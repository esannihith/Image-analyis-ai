import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { useSocket } from './SocketContext';
import { MessageType } from '../types/chat';

interface ChatContextType {
  messages: MessageType[];
  isTyping: boolean;
  uploadProgress: number;
  sendMessage: (content: string) => void;
  uploadImage: (file: File) => Promise<string>;
  clearHistory: () => void;
}

const ChatContext = createContext<ChatContextType>({
  messages: [],
  isTyping: false,
  uploadProgress: 0,
  sendMessage: () => {},
  uploadImage: async () => '',
  clearHistory: () => {},
});

export const useChat = () => useContext(ChatContext);

interface ChatProviderProps {
  children: React.ReactNode;
}

export const ChatProvider: React.FC<ChatProviderProps> = ({ children }) => {
  const [messages, setMessages] = useState<MessageType[]>([]);
  const [isTyping, setIsTyping] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  
  const { socket, isConnected, sessionId, sendPrompt, setActiveImage: socketSetActiveImage } = useSocket();
  const timeoutRef = useRef<number | null>(null);

  // Initialize and listen for socket events
  useEffect(() => {
    if (!socket) return;

    // Listen for answers from the server
    socket.on('answer', (data: { session_id: string, answer: string }) => {
      if (data.session_id === sessionId) {
        const newMessage: MessageType = {
          role: 'assistant',
          content: data.answer,
          timestamp: Date.now()
        };
        setMessages(prev => [...prev, newMessage]);
        setIsTyping(false);
      }
    });

    // Listen for typing indicators
    socket.on('typing', (data: { session_id: string, status: boolean }) => {
      if (data.session_id === sessionId) {
        setIsTyping(data.status);
      }
    });

    // Listen for upload confirmations
    socket.on('upload_ack', (data: { session_id: string, image_id: string, filename: string }) => {
      if (data.session_id === sessionId) {
        setUploadProgress(100);
        
        // Set active image on the server
        socketSetActiveImage(data.image_id);
      }
    });

    // Listen for errors
    socket.on('error', (data: { msg: string }) => {
      const errorMessage: MessageType = {
        role: 'assistant',
        content: `Error: ${data.msg}`,
        timestamp: Date.now()
      };
      setMessages(prev => [...prev, errorMessage]);
      setIsTyping(false);
    });

    return () => {
      socket.off('answer');
      socket.off('typing');
      socket.off('upload_ack');
      socket.off('active_image_set');
      socket.off('error');
    };
  }, [socket, sessionId, socketSetActiveImage]);

  // Send a message to the server
  const sendMessage = useCallback((content: string) => {
    // Don't send empty messages
    if (!content.trim()) return;

    // Add message to local state immediately
    const userMessage: MessageType = {
      role: 'user',
      content,
      timestamp: Date.now()
    };
    setMessages(prev => [...prev, userMessage]);    // Check if socket is connected before trying to send
    if (!socket || !isConnected) {
      // Set typing indicator briefly to simulate attempt at connection
      setIsTyping(true);
      
      // Show connection error after a short delay to make it feel more natural
      setTimeout(() => {
        setIsTyping(false);
        const connectionErrorMessage: MessageType = {
          role: 'assistant',
          content: 'I\'m currently unable to connect to the server. Please check your internet connection and try again later.',
          timestamp: Date.now()
        };
        setMessages(prev => [...prev, connectionErrorMessage]);
      }, 2500); // 2.5 second delay
      
      return;
    }

    // Send to server
    sendPrompt(content);
    
    // Set typing indicator
    setIsTyping(true);
    
    // Set a timeout to clear typing indicator if the server doesn't respond
    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
    }
    
    timeoutRef.current = window.setTimeout(() => {
      setIsTyping(false);
      const timeoutMessage: MessageType = {
        role: 'assistant',
        content: 'The server is taking too long to respond. Please try again.',
        timestamp: Date.now()
      };
      setMessages(prev => [...prev, timeoutMessage]);
    }, 60000); // 60 second timeout
  }, [sendPrompt, socket, isConnected]);
  // Upload an image to the server and add it to the chat
  const uploadImage = useCallback(async (file: File): Promise<string> => {
    try {
      setUploadProgress(0);
        // Check if socket is connected before trying to upload
      if (!socket || !isConnected) {
        // Show small upload progress to indicate an attempt
        setUploadProgress(10);
        
        // Wait a moment before showing the error
        await new Promise(resolve => setTimeout(resolve, 2000));
        
        setUploadProgress(0);
        throw new Error("I'm currently unable to connect to the server. Please check your internet connection and try again later.");
      }
      
      // Create form data
      const formData = new FormData();
      formData.append('file', file);
      formData.append('session_id', sessionId);
      
      // Get backend URL
      const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
      
      // Create a local object URL for immediate display
      const objectUrl = URL.createObjectURL(file);
        // Add a temporary message with the image
      const imageMessage: MessageType = {
        role: 'user',
        content: '',
        timestamp: Date.now(),
        image: {
          id: 'temp',
          url: objectUrl,
          filename: file.name // Include filename as required by the interface
        }
      };
      setMessages(prev => [...prev, imageMessage]);
      
      // Create XMLHttpRequest to track progress
      const xhr = new XMLHttpRequest();
      
      // Setup a promise to handle the response
      const uploadPromise = new Promise<string>((resolve, reject) => {
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            const progress = Math.round((event.loaded / event.total) * 100);
            setUploadProgress(progress);
          }
        });
        
        xhr.onreadystatechange = () => {
          if (xhr.readyState === 4) {
            if (xhr.status >= 200 && xhr.status < 300) {
              try {
                const response = JSON.parse(xhr.responseText);
                  // Update the temporary message with the actual image info
                setMessages(prev => prev.map(msg => {
                  if (msg.timestamp === imageMessage.timestamp && msg.image?.id === 'temp') {
                    return {
                      ...msg,
                      image: {
                        id: response.image_id,
                        filename: response.filename,
                        url: `${backendUrl}/uploads/${response.filename}`
                      }
                    };
                  }
                  return msg;
                }));
                
                resolve(response.image_id);
              } catch (error) {
                reject(new Error('Invalid response from server'));
              }            } else {
              let errorMessage;
              switch (xhr.status) {
                case 0:
                  errorMessage = 'Could not connect to server. Please check your internet connection.';
                  break;
                case 413:
                  errorMessage = 'The image is too large. Please try with a smaller image.';
                  break;
                case 415:
                  errorMessage = 'Unsupported file type. Please upload a valid image file.';
                  break;
                case 401:
                case 403:
                  errorMessage = 'You do not have permission to upload this file.';
                  break;
                case 500:
                  errorMessage = 'Server error occurred. Please try again later.';
                  break;
                default:
                  errorMessage = `Upload failed (Error ${xhr.status})`;
              }
              reject(new Error(errorMessage));
            }
          }
        };
          xhr.onerror = () => {
          reject(new Error('Could not connect to the server. Please check your internet connection and try again.'));
        };
        
        xhr.ontimeout = () => {
          reject(new Error('The server took too long to respond. Please try again later.'));
        };

        // Set a timeout for the request
        xhr.timeout = 15000; // 15 seconds timeout
      });
      
      // Open and send the request
      xhr.open('POST', `${backendUrl}/upload`);
      xhr.send(formData);
      
      // Wait for the upload to complete and return the image ID
      return await uploadPromise;
        } catch (error) {
      console.error('Error uploading image:', error);
      
      // Create a user-friendly error message
      const errorMessage: MessageType = {
        role: 'assistant',
        content: `${error instanceof Error ? error.message : 'Sorry, there was a problem uploading your image. Please try again.'}`,
        timestamp: Date.now()
      };
      
      // Remove the temporary message if it exists
      setMessages(prev => {
        // Find and remove the temp message first
        const withoutTempImage = prev.filter(msg => !(msg.image?.id === 'temp' && msg.role === 'user' && msg.content === ''));
        // Then add the error message
        return [...withoutTempImage, errorMessage];
      });
      
      setUploadProgress(0);
      throw error;
    }
  }, [sessionId, socketSetActiveImage]);

  // Clear chat history
  const clearHistory = useCallback(() => {
    setMessages([]);
  }, []);

  return (
    <ChatContext.Provider
      value={{
        messages,
        isTyping,
        uploadProgress,
        sendMessage,
        uploadImage,
        clearHistory,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};