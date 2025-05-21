import React, { useEffect, useRef } from 'react';
import Message from './Message';
import { useChat } from '../../contexts/ChatContext';

const MessageList: React.FC = () => {
  const { messages, isTyping } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change or typing status changes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-850">
      {messages.length === 0 ? (
        <div className="flex items-center justify-center h-full text-gray-500">
          <div className="text-center">
            <p>Upload an image and start a conversation</p>
            <p className="text-sm mt-2">Ask questions like "What camera settings were used?" or "Where was this taken?"</p>
          </div>
        </div>
      ) : (
        <>
          {messages.map((message, index) => (
            <Message key={index} message={message} />
          ))}
          
          {isTyping && (
            <div className="flex justify-start animate-pulse">
              <div className="bg-gray-700 text-white rounded-lg px-4 py-2 max-w-[80%]">
                <div className="flex space-x-2">
                  <div className="w-2 h-2 rounded-full bg-gray-300 animate-bounce"></div>
                  <div className="w-2 h-2 rounded-full bg-gray-300 animate-bounce delay-75"></div>
                  <div className="w-2 h-2 rounded-full bg-gray-300 animate-bounce delay-150"></div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;