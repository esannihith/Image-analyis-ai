# Image Upload Implementation Guide

This document explains how the frontend uploads images to the backend using HTTP requests while maintaining Socket.IO for real-time messaging.

## Architecture Overview

1. **HTTP Upload**: Images are uploaded via `POST /upload` using `multipart/form-data`
2. **Socket.IO**: Used for real-time messaging and receiving metadata results

## Frontend Implementation

### Image Upload Process

1. When a user selects or drops an image:
   - The frontend creates a FormData object and appends the image with the key `file`
   - The socket ID is included to help the backend route responses back to the correct client
   - The request is sent as a standard `POST` request to `/upload` endpoint
   - Upload progress is tracked and displayed to the user

2. After successful upload:
   - The backend processes the image and extracts metadata
   - The backend uses the Socket.IO connection to emit a `metadata_result` event
   - The frontend listens for this event and updates the UI accordingly

### Key Components

1. **ChatContext.tsx**: Contains the main logic for uploading images via HTTP and managing Socket.IO events
2. **ImageUploader.tsx**: UI for uploading images with drag-and-drop support and progress tracking
3. **SocketContext.tsx**: Manages the WebSocket connection

## Backend Implementation

The backend provides:

1. A RESTful endpoint at `/upload` for receiving images via HTTP POST
2. Socket.IO events for real-time communication:
   - `metadata_result`: Sends image metadata and analysis
   - `message`: Sends chat messages
   - `typing`: Indicates when the AI is processing
   - `error`: Sends error messages

## Integration Guide

### Frontend Requirements

- Include the Socket.ID in the upload request to associate the HTTP request with the Socket.IO connection
- Maintain WebSocket connection for receiving results
- Handle progress tracking for improved UX

### Backend Requirements

- Accept `multipart/form-data` with the image under the key `file`
- Use the provided Socket.ID to emit results back to the correct client
- Send metadata result via Socket.IO

## Error Handling

- Network errors during upload: Displayed in the UI with retry options
- Invalid file types: Rejected before upload with user feedback
- Server errors: Communicated via Socket.IO error events

## Security Considerations

- File size limits: Maximum 5MB
- File type restrictions: Only JPEG and PNG images
- No authentication currently implemented (public anonymous interface)
