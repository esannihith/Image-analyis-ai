// This hook is just a re-export of our context.
// It can be expanded if we need more socket-specific functionality.
import { useSocket as useSocketContext } from '../contexts/SocketContext';

export const useSocket = useSocketContext;