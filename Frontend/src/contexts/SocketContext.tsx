import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';
import { v4 as uuidv4 } from 'uuid';

// Define types for socket events based on our contract
interface SocketContextType {
  socket: Socket | null;
  isConnected: boolean;
  sessionId: string;
  error: string | null;
  join: () => void;
  sendPrompt: (prompt: string) => void;
  setActiveImage: (imageId: string) => void;
  // Removed getHistory for ephemeral setup
}

const SocketContext = createContext<SocketContextType>({
  socket: null,
  isConnected: false,
  sessionId: '',
  error: null,
  join: () => {},
  sendPrompt: () => {},
  setActiveImage: () => {},
  // Removed getHistory for ephemeral setup
});

export const useSocket = () => useContext(SocketContext);

interface SocketProviderProps {
  children: React.ReactNode;
}

export const SocketProvider: React.FC<SocketProviderProps> = ({ children }) => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Get session ID from localStorage or create a new one
  const storedSessionId = localStorage.getItem('session_id');
  const [sessionId, setSessionId] = useState<string>(storedSessionId || uuidv4());
  
  // Store session ID in localStorage when it changes
  useEffect(() => {
    localStorage.setItem('session_id', sessionId);
  }, [sessionId]);

  // Initialize Socket.IO connection
  useEffect(() => {
    // Backend URL (fallback to localhost)
    const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
    
    // Initialize Socket.IO client
    const socketInstance = io(backendUrl, {
      transports: ['websocket'],
      autoConnect: true,
    });

    // Setup event listeners
    socketInstance.on('connect', () => {
      console.log('Socket connected');
      setIsConnected(true);
      setError(null);
      
      // Auto-join the session room on connect
      socketInstance.emit('join', { session_id: sessionId });
    });

    socketInstance.on('disconnect', () => {
      console.log('Socket disconnected');
      setIsConnected(false);
    });

    socketInstance.on('connect_error', (err) => {
      console.error('Connection error:', err);
      setIsConnected(false);
      setError('Could not connect to the server. Please check your internet connection.');
    });

    socketInstance.on('error', (data: { msg: string }) => {
      console.error('Socket error:', data.msg);
      setError(data.msg);
    });

    socketInstance.on('joined', (data: { session_id: string }) => {
      console.log(`Joined session: ${data.session_id}`);
      
      // If we received a different session ID, update our state
      if (data.session_id !== sessionId) {
        setSessionId(data.session_id);
        localStorage.setItem('session_id', data.session_id);
      }
    });

    setSocket(socketInstance);

    return () => {
      socketInstance.disconnect();
    };
  }, [sessionId]);

  // Join a session room
  const join = useCallback(() => {
    if (socket && isConnected) {
      socket.emit('join', { session_id: sessionId });
    }
  }, [socket, isConnected, sessionId]);

  // Send a text prompt to the server
  const sendPrompt = useCallback(
    (prompt: string) => {
      if (socket && isConnected) {
        socket.emit('prompt', { session_id: sessionId, prompt });
      } else {
        setError('Not connected to server. Please try again later.');
      }
    },
    [socket, isConnected, sessionId]
  );

  // Set the active image for analysis
  const setActiveImage = useCallback(
    (imageId: string) => {
      if (socket && isConnected) {
        socket.emit('set_active_image', { session_id: sessionId, image_id: imageId });
      } else {
        setError('Not connected to server. Please try again later.');
      }
    },
    [socket, isConnected, sessionId]
  );

  return (
    <SocketContext.Provider 
      value={{ 
        socket, 
        isConnected, 
        sessionId,
        error,
        join, 
        sendPrompt, 
        setActiveImage, 
        // Removed getHistory for ephemeral setup
      }}
    >
      {children}
    </SocketContext.Provider>
  );
};