import React from 'react';
import { SocketProvider } from './contexts/SocketContext';
import { ChatProvider } from './contexts/ChatContext';
import Layout from './components/Layout/Layout';
import './index.css';

function App() {
  return (
    <SocketProvider>
      <ChatProvider>
        <Layout />
      </ChatProvider>
    </SocketProvider>
  );
}

export default App;