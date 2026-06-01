import React from 'react';
import { Container, Box, Typography } from '@mui/material';
import OrderPage from './pages/OrderPage';

function App() {
  return (
    <Container maxWidth="lg">
      <Box sx={{ my: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom align="center">
          Inventory & Order Management System
        </Typography>
        <OrderPage />
      </Box>
    </Container>
  );
}

export default App;