import React from 'react';
    import { Box, Typography, Alert } from '@mui/material';

    interface ErrorMessageProps {
      message: string;
    }

    const ErrorMessage: React.FC<ErrorMessageProps> = ({ message }) => {
      return (
        <Box sx={{ mt: 4, textAlign: 'center' }}>
          <Alert severity="error">
            <Typography variant="h6">Error</Typography>
            <Typography variant="body1">{message}</Typography>
          </Alert>
        </Box>
      );
    };

    export default ErrorMessage;