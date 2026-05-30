import { Sequelize } from 'sequelize';
import config from '../config';
import Session from '../models/Session';
import SessionItem from '../models/SessionItem';
import RecoveryLog from '../models/RecoveryLog';

const sequelize = new Sequelize(config.databaseUrl, {
  dialect: 'sqlite',
  logging: config.nodeEnv === 'development' ? console.log : false,
});

// Initialize models
Session.initialize(sequelize);
SessionItem.initialize(sequelize);
RecoveryLog.initialize(sequelize);

// Define associations
Session.hasMany(SessionItem, { foreignKey: 'session_id' });
SessionItem.belongsTo(Session, { foreignKey: 'session_id' });

Session.hasMany(RecoveryLog, { foreignKey: 'session_id' });
RecoveryLog.belongsTo(Session, { foreignKey: 'session_id' });

export const initializeDatabase = async () => {
  try {
    await sequelize.sync({ alter: true }); // Use alter: true to safely modify existing tables
    console.log('Database synchronized successfully.');
  } catch (error) {
    console.error('Error synchronizing database:', error);
    throw error;
  }
};

export default sequelize;