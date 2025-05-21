import React, { useState, useRef, useEffect } from 'react';
import { SendIcon, ImageIcon, X } from 'lucide-react';
import { useChat } from '../../contexts/ChatContext';
import Button from '../common/Button';

const MessageInput: React.FC = () => {
  const [input, setInput] = useState('');
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textAreaRef = useRef<HTMLTextAreaElement>(null);
  const { sendMessage, uploadImage, isTyping, uploadProgress } = useChat();

  // Auto-resize text area based on content
  useEffect(() => {
    if (textAreaRef.current) {
      // Reset height to auto to get the correct scrollHeight
      textAreaRef.current.style.height = 'auto';
      
      // Calculate the new height (with a max height limit)
      const newHeight = Math.min(textAreaRef.current.scrollHeight, 150);
      
      // Set the new height
      textAreaRef.current.style.height = `${newHeight}px`;
    }
  }, [input]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (isTyping) return;
    
    // If there's an image to upload, upload it first
    if (selectedFile) {
      try {
        // Clear the image preview before upload starts
        // This prevents the preview from showing after the message is added to chat
        const fileToUpload = selectedFile;
        setImagePreview(null);
        setSelectedFile(null);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
        
        await uploadImage(fileToUpload);
      } catch (error) {
        console.error('Failed to upload image:', error);
        return;
      }
    }
    
    // If there's text to send, send it
    if (input.trim()) {
      sendMessage(input);
      setInput('');
    }
  };
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      
      // Validate file type
      if (!file.type.startsWith('image/')) {
        alert('Please select an image file');
        return;
      }
      
      // Validate file size (limit to 10MB)
      if (file.size > 10 * 1024 * 1024) {
        alert('File size should be less than 10MB');
        return;
      }
      
      setSelectedFile(file);
      
      // Create a preview URL
      const reader = new FileReader();
      reader.onload = (event) => {
        setImagePreview(event.target?.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleImageClick = () => {
    fileInputRef.current?.click();
  };

  const removeSelectedImage = () => {
    setImagePreview(null);
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="border-t border-gray-700 p-4 bg-gray-800">
      {/* Image preview */}
      {imagePreview && (
        <div className="flex items-center mb-3 bg-gray-700 rounded-md p-2 max-w-fit">
          <div className="relative mr-2">
            <img 
              src={imagePreview} 
              alt="Preview" 
              className="h-10 w-10 rounded-md object-cover border border-gray-600"
            />
            <button
              onClick={removeSelectedImage}
              className="absolute -top-2 -right-2 bg-gray-800 text-white p-1 rounded-full border border-gray-600 hover:bg-gray-900 transition-colors"
              type="button"
              aria-label="Remove image"
            >
              <X size={12} />
            </button>
          </div>
          <span className="text-sm text-gray-300 truncate max-w-xs">
            {selectedFile?.name || 'Image attachment'}
          </span>
        </div>
      )}
      
      {/* Upload progress indicator */}
      {uploadProgress > 0 && uploadProgress < 100 && (
        <div className="w-full flex items-center mb-3">
          <div className="w-full bg-gray-700 rounded-full h-2.5 mr-2">
            <div 
              className="bg-blue-600 h-2.5 rounded-full transition-all duration-300" 
              style={{ width: `${uploadProgress}%` }}
            ></div>
          </div>
          <span className="text-xs text-gray-400 min-w-[40px] text-right">
            {Math.round(uploadProgress)}%
          </span>
        </div>
      )}
      
      <form onSubmit={handleSubmit} className="flex items-center space-x-2">
        <textarea
          ref={textAreaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={isTyping ? "AI is typing..." : "Type a message or upload an image..."}
          disabled={isTyping}
          rows={1}
          className="flex-1 bg-gray-700 border border-gray-600 rounded-lg py-2.5 px-4 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed resize-none min-h-[42px] max-h-[150px] overflow-y-auto"
          onKeyDown={(e) => {
            // Submit on Enter (without Shift key)
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (input.trim() || selectedFile) {
                handleSubmit(e as any);
              }
            }
          }}
        />
        
        <input 
          type="file" 
          ref={fileInputRef}
          onChange={handleFileSelect}
          accept="image/*"
          className="hidden"
        />
          
        <Button 
          type="button"
          onClick={handleImageClick}
          disabled={isTyping}
          variant="secondary"
          size="md"
          className={`rounded-full min-w-[42px] h-[42px] p-0 flex items-center justify-center ${
            selectedFile ? 'bg-blue-600 hover:bg-blue-700' : ''
          }`}
          title="Upload image"
        >
          <ImageIcon size={20} />
        </Button>
        
        <Button 
          type="submit"
          disabled={(!input.trim() && !selectedFile) || isTyping}
          variant="primary"
          size="md"
          className="rounded-full min-w-[42px] h-[42px] p-0 flex items-center justify-center"
        >
          <SendIcon size={20} />
        </Button>
      </form>
    </div>
  );
};

export default MessageInput;
