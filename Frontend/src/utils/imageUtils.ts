/**
 * Utility functions for handling images
 */

/**
 * Validates if a file is an acceptable image type
 */
export const isValidImageType = (file: File): boolean => {
  const acceptableTypes = ['image/jpeg', 'image/png', 'image/jpg'];
  return acceptableTypes.includes(file.type);
};

/**
 * Validates if a file size is under the maximum allowed
 */
export const isValidImageSize = (file: File, maxSizeInMB = 5): boolean => {
  const maxSizeInBytes = maxSizeInMB * 1024 * 1024;
  return file.size <= maxSizeInBytes;
};

/**
 * Formats a file size into a readable string
 */
export const formatFileSize = (sizeInBytes: number): string => {
  if (sizeInBytes < 1024) {
    return `${sizeInBytes} bytes`;
  } else if (sizeInBytes < 1048576) {
    return `${(sizeInBytes / 1024).toFixed(1)} KB`;
  } else {
    return `${(sizeInBytes / 1048576).toFixed(1)} MB`;
  }
};

/**
 * Extracts a filename without its extension
 */
export const getFilenameWithoutExtension = (filename: string): string => {
  return filename.replace(/\.[^/.]+$/, '');
};