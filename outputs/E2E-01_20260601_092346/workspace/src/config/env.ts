// src/config/env.ts
interface EnvConfig {
  API_BASE_URL: string;
}

const getEnvConfig = (): EnvConfig => {
  const API_BASE_URL = import.meta.env.REACT_APP_API_URL;

  if (!API_BASE_URL) {
    console.error('Environment variable REACT_APP_API_URL is not defined.');
    // In a real application, you might throw an error or provide a default.
    // For now, we'll use an empty string, but this will likely cause API calls to fail.
    // Consider adding a robust error handling or a fallback URL.
    // throw new Error('REACT_APP_API_URL is not defined in the environment variables.');
  }

  return {
    API_BASE_URL: API_BASE_URL || '', // Fallback to empty string if not defined
  };
};

export const envConfig = getEnvConfig();