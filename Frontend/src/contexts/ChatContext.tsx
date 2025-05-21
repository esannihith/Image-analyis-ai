import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { useSocket } from './SocketContext';
import { MessageType } from '../types/chat';

interface ChatContextType {
  messages: MessageType[];
  isTyping: boolean;
  uploadProgress: number;
  sendMessage: (content: string, imageId?: string) => void;
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
  
  const { socket, isConnected, sessionId } = useSocket();
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
      socket.off('error');
    };
  }, [socket, sessionId]);

  // Send a message to the server (Q&A)
  const sendMessage = useCallback((content: string, imageId?: string) => {
    if (!content.trim()) return;
    const userMessage: MessageType = {
      role: 'user',
      content,
      timestamp: Date.now()
    };
    setMessages(prev => [...prev, userMessage]);
    if (!socket || !isConnected) {
      setIsTyping(true);
      setTimeout(() => {
        setIsTyping(false);
        const connectionErrorMessage: MessageType = {
          role: 'assistant',
          content: 'I\'m currently unable to connect to the server. Please check your internet connection and try again later.',
          timestamp: Date.now()
        };
        setMessages(prev => [...prev, connectionErrorMessage]);
      }, 2500);
      return;
    }
    // Always require imageId for Q&A
    if (!imageId) {
      setIsTyping(false);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Please upload an image before asking a question.',
        timestamp: Date.now()
      }]);
      return;
    }
    socket.emit('user_question', {
      session_id: sessionId,
      image_id: imageId,
      question: content
    });
    setIsTyping(true);
    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = window.setTimeout(() => {
      setIsTyping(false);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'The server is taking too long to respond. Please try again.',
        timestamp: Date.now()
      }]);
    }, 60000);
  }, [socket, isConnected, sessionId]);

  // Upload an image to the server and add it to the chat
  const uploadImage = useCallback(async (file: File): Promise<string> => {
    try {
      setUploadProgress(0);
      if (!socket || !isConnected) {
        setUploadProgress(10);
        await new Promise(resolve => setTimeout(resolve, 2000));
        setUploadProgress(0);
        throw new Error("I'm currently unable to connect to the server. Please check your internet connection and try again later.");
      }
      // Create form data
      const formData = new FormData();
      formData.append('file', file);
      formData.append('session_id', sessionId);
      const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
      const objectUrl = URL.createObjectURL(file);
      const imageMessage: MessageType = {
        role: 'user',
        content: '',
        timestamp: Date.now(),
        image: {
          id: 'temp',
          url: objectUrl,
          filename: file.name
        }
      };
      setMessages(prev => [...prev, imageMessage]);
      const xhr = new XMLHttpRequest();
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
                const response = JSON.parse(xhr.responseText);                setMessages(prev => prev.map(msg => {
                  if (msg.timestamp === imageMessage.timestamp && msg.image?.id === 'temp') {
                    return {
                      ...msg,
                      image: {
                        id: response.image_id,
                        filename: file.name,
                        url: `${backendUrl}/uploads/${response.image_id}`
                      }
                    };
                  }
                  return msg;
                }));
                resolve(response.image_id);
              } catch (error) {
                reject(new Error('Invalid response from server'));
              }
            } else {
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
        xhr.timeout = 15000;
      });
      xhr.open('POST', `${backendUrl}/upload`);
      xhr.send(formData);
      return await uploadPromise;
    } catch (error) {
      console.error('Error uploading image:', error);
      const errorMessage: MessageType = {
        role: 'assistant',
        content: `${error instanceof Error ? error.message : 'Sorry, there was a problem uploading your image. Please try again.'}`,
        timestamp: Date.now()
      };
      setMessages(prev => {
        const withoutTempImage = prev.filter(msg => !(msg.image?.id === 'temp' && msg.role === 'user' && msg.content === ''));
        return [...withoutTempImage, errorMessage];
      });
      setUploadProgress(0);
      throw error;
    }
  }, [sessionId, socket, isConnected]);

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