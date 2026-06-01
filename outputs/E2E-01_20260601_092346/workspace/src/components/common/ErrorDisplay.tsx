// src/components/common/ErrorDisplay.tsx
import React from 'react';
import { Box, Alert, AlertTitle, Typography } from '@mui/material';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';

interface ErrorDisplayProps {
  message: string;
  title?: string;
}

const ErrorDisplay: React.FC<ErrorDisplayProps> = ({ message, title = 'Error' }) => {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        width: '100%',
        p: 2,
      }}
    >
      <Alert severity="error" icon={<ErrorOutlineIcon fontSize="inherit" />} sx={{ width: '100%', maxWidth: 500 }}>
        <AlertTitle>{title}</AlertTitle>
        <Typography variant="body1">{message}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Please try again later or contact support.
        </Typography>
      </Alert>
    </Box>
  );
};

export default ErrorDisplay;