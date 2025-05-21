import React from 'react';
import { ImageIcon } from 'lucide-react';

interface ImagePreviewProps {
  imageUrl: string;
}

const ImagePreview: React.FC<ImagePreviewProps> = ({ imageUrl }) => {
  if (!imageUrl) return null;

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-full overflow-hidden rounded-lg border border-gray-700 bg-gray-900">
        <div className="absolute inset-0 flex items-center justify-center bg-gray-900">
          <ImageIcon className="h-10 w-10 text-gray-600" />
        </div>
        <img
          src={imageUrl}
          alt="Uploaded"
          className="relative z-10 w-full object-contain max-h-[450px]"
          onError={(e) => {
            e.currentTarget.onerror = null;
            e.currentTarget.style.display = 'none';
          }}
        />
      </div>
      <div className="w-full mt-4">
        <h3 className="text-sm font-medium text-gray-400 mb-1">Image Details</h3>
        <div className="p-3 bg-gray-850 rounded border border-gray-700 text-sm">
          <p className="text-gray-400">The image details will be analyzed by the AI.</p>
          <p className="text-gray-400 mt-1">Ask questions in the chat to learn more about the image.</p>
        </div>
      </div>
    </div>
  );
};

export default ImagePreview;