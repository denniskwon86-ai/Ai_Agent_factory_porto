import React from 'react';
import { Typography, Box } from '@mui/material';

const HomePage: React.FC = () => {
  return (
    <Box sx={{ my: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Welcome to the Inventory Management System!
      </Typography>
      <Typography variant="body1">
        Use the navigation bar above to manage materials, inventory, and orders.
      </Typography>
    </Box>
  );
};

export default HomePage;