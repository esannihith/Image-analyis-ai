import React from 'react';
import Header from './Header';
import Main from './Main';
import { ImageIcon } from 'lucide-react';

const Layout: React.FC = () => {
  return (
    <div className="flex flex-col min-h-screen bg-gray-900 text-gray-200">
      <Header />
      <Main />
      <footer className="py-2 px-6 text-center text-gray-500 text-xs border-t border-gray-800">
        <div className="flex items-center justify-center gap-1">
          <ImageIcon size={12} />
          <span>Conversational Image Analysis © {new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  );
};

export default Layout;