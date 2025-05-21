import React from 'react';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import { useChat } from '../../contexts/ChatContext';

const ChatContainer: React.FC = () => {
  const { isTyping, uploadProgress } = useChat();
  
  return (
    <div className="flex flex-col h-[700px] max-h-[calc(100vh-8rem)]">
      <div className="p-4 border-b border-gray-700 bg-gray-800 flex justify-between items-center">
        <div>
          <h2 className="font-medium text-lg">Chat with AI about your image</h2>
          {uploadProgress > 0 && uploadProgress < 100 && (
            <div className="text-sm text-blue-400 animate-pulse mt-1">
              Uploading image... ({Math.round(uploadProgress)}%)
            </div>
          )}
          {isTyping && (
            <div className="text-sm text-blue-400 animate-pulse mt-1">
              AI is thinking...
            </div>
          )}
        </div>
      </div>
      <MessageList />
      <MessageInput />
    </div>
  );
};

export default ChatContainer;