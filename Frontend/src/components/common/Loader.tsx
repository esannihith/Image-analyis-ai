import React from 'react';

interface LoaderProps {
  size?: 'sm' | 'md' | 'lg';
  color?: 'primary' | 'white' | 'gray';
}

const Loader: React.FC<LoaderProps> = ({ 
  size = 'md', 
  color = 'primary' 
}) => {
  // Size mappings
  const sizeMap = {
    sm: 'h-4 w-4 border-2',
    md: 'h-6 w-6 border-2',
    lg: 'h-8 w-8 border-3',
  };
  
  // Color mappings
  const colorMap = {
    primary: 'border-blue-600 border-t-transparent',
    white: 'border-white border-t-transparent',
    gray: 'border-gray-400 border-t-transparent',
  };

  return (
    <div className="flex items-center justify-center">
      <div 
        className={`
          animate-spin rounded-full
          ${sizeMap[size]} ${colorMap[color]}
        `}
      />
    </div>
  );
};

export default Loader;