import apiClient from './api';

interface User {
  user_id: number;
  username: string;
  email: string;
  role: string;
}

export const fetchUsers = async (): Promise<User[]> => {
  const response = await apiClient.get<User[]>('/users');
  return response.data;
};

// Add other user-related API calls here (e.g., createUser, getUserById)