import React from 'react';
import ChatContainer from '../Chat/ChatContainer';

const Main: React.FC = () => {
  return (
    <main className="flex-1 py-4 px-6 max-w-4xl w-full mx-auto">
      <div className="h-full">
        <div className="flex flex-col bg-gray-800 rounded-lg overflow-hidden border border-gray-700 shadow-lg">
          <ChatContainer />
        </div>
      </div>
    </main>
  );
};

export default Main;