import React from 'react';
import { UserIcon, ServerIcon } from 'lucide-react';
import { MessageType } from '../../types/chat';

interface MessageProps {
  message: MessageType;
}

const Message: React.FC<MessageProps> = ({ message }) => {
  const isUser = message.role === 'user';
  
  // Format the timestamp
  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };
  
  return (
    <div 
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} animate-fadeIn`}
    >
      <div 
        className={`
          flex max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'}
        `}
      >
        <div 
          className={`
            flex items-center justify-center h-8 w-8 rounded-full mx-2 flex-shrink-0 
            ${isUser ? 'bg-blue-600' : 'bg-gray-700'}
          `}
        >
          {isUser ? <UserIcon size={16} /> : <ServerIcon size={16} />}
        </div>
        <div>
          {message.image && (
            <div className="mb-2">
              <img 
                src={message.image.url} 
                alt="Uploaded content" 
                className="max-w-full max-h-80 rounded-lg object-contain border border-gray-600 bg-gray-900"
                onClick={() => window.open(message.image?.url, '_blank')}
                style={{ cursor: 'pointer' }}
              />
            </div>
          )}
          {message.content && (
            <div 
              className={`
                rounded-2xl py-2 px-3 
                ${isUser 
                  ? 'bg-blue-600 text-white rounded-tr-none' 
                  : 'bg-gray-700 text-gray-100 rounded-tl-none'}
              `}
            >
              {message.content}
            </div>
          )}
          <div 
            className={`
              text-xs mt-1 text-gray-500
              ${isUser ? 'text-right mr-2' : 'ml-2'}
            `}
          >
            {formatTime(message.timestamp)}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Message;
