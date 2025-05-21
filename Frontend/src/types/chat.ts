export interface MessageType {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  image?: {
    filename: any;
    id: string;
    url: string;
  };
}

export interface ImageType {
  path: string;
  filename: string;
  added_at: number;
}

export interface SessionType {
  created_at: number;
  messages: MessageType[];
  images: Record<string, ImageType>;
  active_image_id: string | null;
}