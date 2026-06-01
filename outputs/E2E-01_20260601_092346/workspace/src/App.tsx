// src/App.tsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import { Provider } from 'react-redux';
import { store } from './store';
import InventoryPage from './pages/InventoryPage';
import Header from './components/layout/Header';

// Define a custom Material-UI theme
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2', // A shade of blue
    },
    secondary: {
      main: '#dc004e', // A shade of red
    },
    background: {
      default: '#f4f6f8', // Light grey background
    },
  },
  typography: {
    fontFamily: 'Roboto, Arial, sans-serif',
    h4: {
      fontWeight: 600,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none', // Keep button text as is
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#282c34', // Darker header
        },
      },
    },
  },
});

const App: React.FC = () => {
  return (
    <Provider store={store}>
      <ThemeProvider theme={theme}>
        <CssBaseline /> {/* Resets CSS and applies basic Material-UI styles */}
        <Router>
          <Header />
          <Routes>
            <Route path="/" element={<InventoryPage />} />
            {/* Add other routes here */}
            {/* <Route path="/orders" element={<OrdersPage />} /> */}
          </Routes>
        </Router>
      </ThemeProvider>
    </Provider>
  );
};

export default App;