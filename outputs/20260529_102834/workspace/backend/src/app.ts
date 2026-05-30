import express from 'express';
import cors from 'cors';
import sessionRouter from './routers/sessionRouter';
import { errorHandler } from './middleware/errorHandler';
import sequelize from './database';

const app = express();

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Routes
app.use('/api', sessionRouter);

// Global Error Handler
app.use(errorHandler);

// Database Synchronization
const syncDatabase = async () => {
  try {
    await sequelize.sync();
    console.log('Database synchronized successfully.');
  } catch (error) {
    console.error('Error synchronizing database:', error);
  }
};

syncDatabase();

export default app;