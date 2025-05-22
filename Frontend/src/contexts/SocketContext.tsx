import React, { createContext, useContext, useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';

// Define the structure of the service status update payload
interface ServiceStatusPayload {
  status: 'ok' | 'error';
  role: 'assistant'; // Changed from type: 'BOT_MESSAGE'
  title?: string;
  message: string;
  code?: string;
  timestamp: string;
}

interface SocketContextType {
  socket: Socket | null;
  isConnected: boolean;
  sessionId: string;
  error: string | null; // General connection or other errors
  isServiceAvailable: boolean;
  serviceStatusMessage: ServiceStatusPayload | null; // Store the detailed status message
}

const SocketContext = createContext<SocketContextType>({
  socket: null,
  isConnected: false,
  sessionId: '',
  error: null,
  isServiceAvailable: true, // Assume available until told otherwise
  serviceStatusMessage: null,
});

export const useSocket = () => useContext(SocketContext);

interface SocketProviderProps {
  children: React.ReactNode;
}

export const SocketProvider: React.FC<SocketProviderProps> = ({ children }) => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [isServiceAvailable, setIsServiceAvailable] = useState<boolean>(true); // Default to true
  const [serviceStatusMessage, setServiceStatusMessage] = useState<ServiceStatusPayload | null>(null);

  // On mount, clear sessionId for strict ephemeral session
  useEffect(() => {
    // setSessionId(''); // Consider if you want to persist sessionId across refreshes or always new
  }, []);

  useEffect(() => {
    const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
    const socketInstance = io(backendUrl, {
      transports: ['websocket', 'polling'],
      autoConnect: true,
      reconnection: true,
    });

    socketInstance.on('connect', () => {
      console.log('Socket connected successfully');
      setIsConnected(true);
      setError(null);
      // If previously service was unavailable, connecting might mean it's now available,
      // but wait for explicit status or clear old status message.
      // For now, we don't assume service is available on 'connect' if it was previously marked unavailable.
      // The backend should send service_status_update if it becomes available.
      socketInstance.emit('session_init', { session_id: sessionId });
    });

    socketInstance.on('connect_error', (err) => {
      console.error('Socket connection error:', err);
      setIsConnected(false);
      setError(`Connection error: ${err.message}. The server may be temporarily down or unreachable.`);
      setIsServiceAvailable(false); // Connection error implies service is not available
      setServiceStatusMessage({
        status: 'error',
        role: 'assistant', // Changed from type: 'BOT_MESSAGE'
        title: 'Connection Failed',
        message: `Could not connect to the server: ${err.message}. Please check your internet connection and try again.`,
        code: 'CONNECTION_ERROR',
        timestamp: new Date().toISOString(),
      });
    });

    socketInstance.on('disconnect', (reason) => {
      console.log('Socket disconnected:', reason);
      setIsConnected(false);
      // If disconnect was not clean (e.g., server went down), service is likely unavailable.
      if (reason !== 'io client disconnect') { // 'io client disconnect' is when socketInstance.disconnect() is called
        setIsServiceAvailable(false);
        // setServiceStatusMessage if you want a generic "disconnected" message to show as service unavailable
      }
    });

    // Listener for 'session_ready' from backend
    socketInstance.on('session_ready', (data: { session_id: string; ttl: number }) => {
      console.log('Session ready:', data);
      if (data.session_id) { // Ensure session_id is present
        setSessionId(data.session_id);
      }
      // Optionally, clear any generic "connecting" errors here
      setError(null);
    });

    // Listener for the new 'service_status_update'
    socketInstance.on('service_status_update', (data: ServiceStatusPayload) => {
      console.log('Service status update:', data);
      setServiceStatusMessage(data);
      if (data.status === 'error') {
        setIsServiceAvailable(false);
        setError(data.message); // Optionally set general error too
      } else {
        setIsServiceAvailable(true);
        setError(null); // Clear error if service becomes ok
      }
    });
    
    // General error listener (might be less used now with specific events)
    // socketInstance.on('error', (data: { msg: string }) => {
    //   console.error('Generic socket error event:', data);
    //   setError(data.msg);
    // });

    setSocket(socketInstance);

    return () => {
      socketInstance.disconnect();
    };
  // }, [sessionId]); // Removed sessionId from dependency array if it's managed by session_ready
  }, []); // Run once on mount


  return (
    <SocketContext.Provider
      value={{
        socket,
        isConnected,
        sessionId,
        error,
        isServiceAvailable,
        serviceStatusMessage,
      }}
    >
      {children}
    </SocketContext.Provider>
  );
};