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
            <div className="mb-2 relative">
              <div className="relative">
                <div className="absolute inset-0 flex items-center justify-center bg-gray-800 rounded-lg">
                  <div className="animate-pulse flex flex-col items-center text-gray-500">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                      <circle cx="8.5" cy="8.5" r="1.5"></circle>
                      <polyline points="21 15 16 10 5 21"></polyline>
                    </svg>
                    <span className="mt-2 text-xs">Loading image...</span>
                  </div>
                </div>
                <img 
                  src={message.image.url} 
                  alt={message.image.filename || "Uploaded image"} 
                  className="max-w-full max-h-80 rounded-lg object-contain border border-gray-600 bg-gray-900 relative z-10"
                  onClick={() => window.open(message.image?.url, '_blank')}
                  style={{ cursor: 'pointer' }}
                  onError={(e) => {
                    console.error(`Failed to load image: ${message.image?.url}`);
                    e.currentTarget.onerror = null;
                    e.currentTarget.style.display = 'none';
                    const parent = e.currentTarget.parentElement;
                    if (parent) {
                      const errorDiv = document.createElement('div');
                      errorDiv.className = "flex items-center justify-center h-56 bg-gray-800 rounded-lg border border-gray-600";
                      errorDiv.innerHTML = `
                        <div class="text-center p-4">
                          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mx-auto text-red-500 mb-2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="15" y1="9" x2="9" y2="15"></line>
                            <line x1="9" y1="9" x2="15" y2="15"></line>
                          </svg>
                          <p class="text-gray-400">Image could not be loaded</p>
                        </div>
                      `;
                      parent.appendChild(errorDiv);
                    }
                  }}
                  onLoad={(e) => {
                    // Successfully loaded, make sure it's visible
                    e.currentTarget.style.display = 'block';
                  }}
                />
              </div>
              <div className="absolute bottom-2 right-2 bg-black bg-opacity-60 text-white text-xs px-2 py-1 rounded">
                {message.image.filename || "Uploaded image"}
              </div>
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
