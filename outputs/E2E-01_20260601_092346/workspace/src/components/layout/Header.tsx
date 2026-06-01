// src/components/layout/Header.tsx
import React from 'react';
import { AppBar, Toolbar, Typography, Box, Button } from '@mui/material';
import { Link } from 'react-router-dom';
import InventoryIcon from '@mui/icons-material/Inventory';
import { APP_NAME } from '../../config';

const Header: React.FC = () => {
  return (
    <AppBar position="static" sx={{ mb: 4 }}>
      <Toolbar>
        <InventoryIcon sx={{ mr: 1 }} />
        <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
          <Link to="/" style={{ textDecoration: 'none', color: 'inherit' }}>
            {APP_NAME}
          </Link>
        </Typography>
        <Box>
          <Button color="inherit" component={Link} to="/">
            Inventory
          </Button>
          {/* Add more navigation links here if needed */}
          {/* <Button color="inherit" component={Link} to="/orders">
            Orders
          </Button> */}
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default Header;