import { Table, Column, Model, DataType, HasMany } from 'sequelize-typescript';
import SessionItem from './SessionItem';
import RecoveryLog from './RecoveryLog';

@Table({ tableName: 'sessions', timestamps: true })
export default class Session extends Model {
  @Column({
    type: DataType.INTEGER,
    autoIncrement: true,
    primaryKey: true,
  })
  session_id!: number;

  @Column({
    type: DataType.STRING,
    allowNull: false,
  })
  name!: string;

  @Column({
    type: DataType.STRING,
    allowNull: false,
  })
  storage_path!: string;

  @Column({
    type: DataType.BOOLEAN,
    allowNull: false,
    defaultValue: false,
  })
  compression!: boolean;

  @Column({
    type: DataType.BOOLEAN,
    allowNull: false,
    defaultValue: false,
  })
  encryption!: boolean;

  @HasMany(() => SessionItem, { foreignKey: 'session_id', onDelete: 'CASCADE' })
  sessionItems?: SessionItem[];

  @HasMany(() => RecoveryLog, { foreignKey: 'session_id', onDelete: 'CASCADE' })
  recoveryLogs?: RecoveryLog[];
}