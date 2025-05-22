import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { useSocket } from './SocketContext';
import { MessageType } from '../types/chat';

// ServiceStatusPayload interface removed as it should be defined in SocketContext or a shared types file

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
  
  const { socket, isConnected, sessionId, isServiceAvailable, serviceStatusMessage } = useSocket();
  const timeoutRef = useRef<number | null>(null);

  // Effect to handle service status messages from SocketContext
  useEffect(() => {
    if (serviceStatusMessage && serviceStatusMessage.status === 'error') {
      const existingStatus = messages.find(
        (m) => m.isServiceStatus && m.content === `${serviceStatusMessage.title ? `**${serviceStatusMessage.title}**\n` : ''}${serviceStatusMessage.message}`
      );
      if (!existingStatus) {
        const statusMessageContent = `${serviceStatusMessage.title ? `**${serviceStatusMessage.title}**\n` : ''}${serviceStatusMessage.message}`;
        const statusMessage: MessageType = {
          role: 'assistant',
          content: statusMessageContent,
          timestamp: new Date(serviceStatusMessage.timestamp).getTime(),
          isError: true,
          isServiceStatus: true, // Custom flag
        };
        setMessages(prev => [...prev, statusMessage]);
      }
    }
    // Optional: Handle 'ok' status from serviceStatusMessage to clear errors or show "Service available"
  }, [serviceStatusMessage, messages]); // Added messages to dependencies

  // Initialize and listen for socket events
  useEffect(() => {
    if (!socket) return;

    // Updated to match backend payload: { question: string, result: string, session_id?: string }
    const handleAnalysisResult = (data: { question: string, result: string, session_id?: string }) => {
      // session_id check can be here or assume backend filters correctly
      // if (data.session_id && data.session_id !== sessionId) return; 

      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      const newMessage: MessageType = {
        role: 'assistant',
        content: data.result, // Assuming data.result is the text from LLM
        timestamp: Date.now()
      };
      setMessages(prev => [...prev, newMessage]);
      setIsTyping(false);
    };
    
    // General error handler for chat-specific operations
    // Updated payload to match backend: { code?: string, message: string, severity?:string, session_id?: string }
    const handleErrorEvent = (errorData: { code?: string, message: string, severity?:string, session_id?: string, filename?: string }) => {
      // session_id check can be here
      // if (errorData.session_id && errorData.session_id !== sessionId) return;

      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }

      // Avoid displaying redundant errors if a service status message already covers it
      if (serviceStatusMessage && serviceStatusMessage.status === 'error' && 
          (serviceStatusMessage.code === errorData.code || serviceStatusMessage.message === errorData.message) ) {
          return;
      }
      
      let displayMessage = `Error: ${errorData.message}`;
      if (errorData.filename) { // For upload_error context
        displayMessage = `Upload failed for ${errorData.filename}: ${errorData.message}`;
      }
      if (errorData.code) {
        displayMessage += ` (Code: ${errorData.code})`;
      }

      const errorMessage: MessageType = {
        role: 'assistant',
        content: displayMessage,
        timestamp: Date.now(),
        isError: true,
      };
      setMessages(prev => [...prev, errorMessage]);
      setIsTyping(false);
    };
    
    socket.on('analysis_result', handleAnalysisResult);
    socket.on('session_error', handleErrorEvent);
    socket.on('server_error', handleErrorEvent); // Keep for other unexpected server issues
    socket.on('processing_error', handleErrorEvent);
    socket.on('upload_error', handleErrorEvent); // Centralized upload_error handling

    return () => {
      socket.off('analysis_result', handleAnalysisResult);
      socket.off('session_error', handleErrorEvent);
      socket.off('server_error', handleErrorEvent);
      socket.off('processing_error', handleErrorEvent);
      socket.off('upload_error', handleErrorEvent);
    };
  }, [socket, sessionId, serviceStatusMessage]); // Added serviceStatusMessage to dependency array

  // Send a message to the server (Q&A)
  const sendMessage = useCallback((content: string, imageId?: string) => {
    if (!content.trim()) return;

    const userMessage: MessageType = { role: 'user', content, timestamp: Date.now() };
    setMessages(prev => [...prev, userMessage]);

    // Check service availability first
    if (!isServiceAvailable) {
      const existingStatus = messages.find(
        (m) => m.isServiceStatus && m.content === (serviceStatusMessage?.message || "The image analysis service is currently unavailable. Please try again later.")
      );
      // Check against current messages + the user message we just added
      const alreadyDisplayed = messages.concat(userMessage).some(
        (m) => m.isServiceStatus && m.content === (serviceStatusMessage?.message || "The image analysis service is currently unavailable. Please try again later.")
      );

      if (!alreadyDisplayed) {
        const serviceDownMessage: MessageType = {
          role: 'assistant',
          content: serviceStatusMessage?.message || "The image analysis service is currently unavailable. Your message was not sent.",
          timestamp: Date.now(),
          isError: true,
          isServiceStatus: true,
        };
        setMessages(prev => [...prev, serviceDownMessage]);
      }
      return; // Don't attempt to send if service is down
    }

    // This check might be redundant if isServiceAvailable covers it, but kept for robustness
    if (!socket || !isConnected) {
      const connErrorMessage: MessageType = {
        role: 'assistant',
        content: "I'm currently unable to connect to the server. Please check your internet connection. Your message was not sent.",
        timestamp: Date.now(),
        isError: true,
      };
      setMessages(prev => [...prev, connErrorMessage]);
      return; // Don't attempt to send if not connected
    }

    // If service is available and socket is connected, proceed to emit
    // Emit the message to the backend (actual emit logic was missing from the snippet but should be here)
    socket.emit('user_question', {
      question: content,
      session_id: sessionId,
      image_hash: imageId // Assuming imageId is the current_image_hash_focus
    });

    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
    }
    setIsTyping(true); // Set typing indicator for assistant
    timeoutRef.current = window.setTimeout(() => {
      setIsTyping(false);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'The server is taking too long to respond. Please try again.',
        timestamp: Date.now(),
        isError: true, // Keep isError for styling
      }]);
      timeoutRef.current = null;
    }, 60000); // 60 seconds timeout
  }, [socket, isConnected, sessionId, isServiceAvailable, serviceStatusMessage, messages]); // Added messages

  // Upload an image to the server and add it to the chat
  const uploadImage = useCallback(async (file: File): Promise<string> => {
    return new Promise<string>((resolve, reject) => {
      // Check service availability first
      if (!isServiceAvailable) {
        const errorMsgContent = serviceStatusMessage?.message || "Cannot upload: The image analysis service is currently unavailable.";
        const existingStatus = messages.find(m => m.isServiceStatus && m.content === errorMsgContent);
        if(!existingStatus) {
          setMessages(prev => [...prev, { role: 'assistant', content: errorMsgContent, timestamp: Date.now(), isError: true, isServiceStatus: true }]);
        }
        setUploadProgress(0);
        reject(new Error(errorMsgContent));
        return;
      }
      if (!socket || !isConnected || !sessionId) {
        const errorMsg = "Cannot upload: Not connected to server or session not initialized.";
        setMessages(prev => [...prev, { role: 'assistant', content: errorMsg, timestamp: Date.now(), isError: true }]);
        setUploadProgress(0);
        reject(new Error(errorMsg));
        return;
      }

      const tempId = `temp_${Date.now()}_${file.name}`;
      const objectUrl = URL.createObjectURL(file);
      
      const optimisticMessage: MessageType = {
        role: 'user',
        content: '', // Image messages might not have textual content from user initially
        timestamp: Date.now(),
        image: {
          id: tempId,
          url: objectUrl,
          filename: file.name
        }
      };
      setMessages(prev => [...prev, optimisticMessage]);
      setUploadProgress(10); // Initial progress

      const reader = new FileReader();
      reader.readAsArrayBuffer(file);

      reader.onprogress = (event) => {
        if (event.lengthComputable) {
          const progress = Math.round((event.loaded / event.total) * 50); // Reading file is 50% of task
          setUploadProgress(progress);
        }
      };

      reader.onload = () => {
        setUploadProgress(50); // File read complete
        const imageBytes = reader.result as ArrayBuffer;

        const uploadTimeout = setTimeout(() => {
          socket.off('upload_success', successListener); 
          // 'upload_error' is now handled by the general listener in useEffect
          setMessages(prev => prev.filter(msg => msg.image?.id !== tempId)); // Clean optimistic message
          const errorMsg = `Upload timed out for ${file.name}. Please try again.`;
          // Add error to chat via handleErrorEvent or directly if more context needed for timeout
          const timeoutError: MessageType = { role: 'assistant', content: errorMsg, timestamp: Date.now(), isError: true };
          setMessages(prev => [...prev, timeoutError]);
          setUploadProgress(0);
          reject(new Error(errorMsg));
        }, 30000); 

        // Backend sends: { image_hash: string; filename: string; session_id: string, message?: string, position?: number }
        const successListener = (data: { image_hash: string; filename: string; session_id: string, message?: string, position?: number }) => {
          if (data.session_id === sessionId && data.filename === file.name) {
            clearTimeout(uploadTimeout);
            socket.off('upload_success', successListener); // Remove this specific listener
            
            setMessages(prev => prev.map(msg => 
              msg.image?.id === tempId 
                ? { ...msg, image: { ...msg.image!, id: data.image_hash, isLoading: false } } // Use image_hash
                : msg
            ));
            if (data.message) { // Optional success message from backend
                const successMessage: MessageType = {
                    role: 'assistant', 
                    content: data.message, // data.message is a string here because of the if-check
                    timestamp: Date.now()
                };
                setMessages(prev => [...prev, successMessage]);
            }
            setUploadProgress(100);
            resolve(data.image_hash); // Resolve with image_hash
            setTimeout(() => setUploadProgress(0), 1000);
          }
        };
        
        // 'upload_error' is now handled by the global handler.
        // No temporary error listener needed here anymore.
        socket.on('upload_success', successListener);
        
        socket.emit('upload_image', {
          session_id: sessionId,
          filename: file.name,
          file: imageBytes,
          metadata: {} // Can be extended later
        });
        setUploadProgress(60); // Emitted, waiting for server ack
      };

      reader.onerror = () => {
        setMessages(prev => prev.filter(msg => msg.image?.id !== tempId)); // Clean optimistic message
        const errorMsg = `Could not read file ${file.name}.`;
        const readerError: MessageType = { role: 'assistant', content: errorMsg, timestamp: Date.now(), isError: true };
        setMessages(prev => [...prev, readerError]);
        setUploadProgress(0);
        reject(new Error(errorMsg));
      };
    });
  }, [socket, isConnected, sessionId, isServiceAvailable, serviceStatusMessage, messages]); // Added messages

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