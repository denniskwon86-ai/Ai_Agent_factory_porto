import { Sequelize } from 'sequelize-typescript';
import config from '../config';
import Session from '../models/Session';
import SessionItem from '../models/SessionItem';
import RecoveryLog from '../models/RecoveryLog';

const sequelize = new Sequelize({
  dialect: 'sqlite',
  storage: config.DATABASE_URL.replace('sqlite:', ''),
  models: [Session, SessionItem, RecoveryLog],
  logging: config.NODE_ENV === 'development' ? console.log : false,
});

export default sequelize;