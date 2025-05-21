import React, { createContext, useContext, useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';

interface SocketContextType {
  socket: Socket | null;
  isConnected: boolean;
  sessionId: string;
  error: string | null;
}

const SocketContext = createContext<SocketContextType>({
  socket: null,
  isConnected: false,
  sessionId: '',
  error: null,
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

  // On mount, clear sessionId for strict ephemeral session
  useEffect(() => {
    setSessionId('');
  }, []);

  useEffect(() => {
    const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';    const socketInstance = io(backendUrl, {
      transports: ['websocket', 'polling'],
      autoConnect: true,
      reconnection: true,
    });    socketInstance.on('connect', () => {
      console.log('Socket connected successfully');
      setIsConnected(true);
      setError(null);
      // Always emit session_init after connect (with sessionId or empty)
      socketInstance.emit('session_init', { session_id: sessionId });
    });

    socketInstance.on('connect_error', (err) => {
      console.error('Socket connection error:', err);
      setError(`Connection error: ${err.message}`);
    });

    socketInstance.on('disconnect', (reason) => {
      console.log('Socket disconnected:', reason);
      setIsConnected(false);
    });

    socketInstance.on('connect_error', (err) => {
      setIsConnected(false);
      setError(`Could not connect to the server: ${err.message}. Please check your internet connection.`);
    });

    socketInstance.on('session', (data: { session_id: string }) => {
      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id);
      }
    });

    socketInstance.on('error', (data: { msg: string }) => {
      setError(data.msg);
    });

    setSocket(socketInstance);
    return () => {
      socketInstance.disconnect();
    };

  }, []);

  return (
    <SocketContext.Provider 
      value={{ 
        socket, 
        isConnected, 
        sessionId,
        error
      }}
    >
      {children}
    </SocketContext.Provider>
  );
};