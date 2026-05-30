import { Table, Column, Model, DataType, ForeignKey } from 'sequelize-typescript';
import Session from './Session';

@Table({ tableName: 'recovery_logs', timestamps: true })
export default class RecoveryLog extends Model {
  @Column({
    type: DataType.INTEGER,
    autoIncrement: true,
    primaryKey: true,
  })
  log_id!: number;

  @ForeignKey(() => Session)
  @Column({
    type: DataType.INTEGER,
    allowNull: false,
  })
  session_id!: number;

  @Column({
    type: DataType.STRING,
    allowNull: false,
  })
  item_path!: string;

  @Column({
    type: DataType.STRING,
    allowNull: false,
  })
  action_type!: string;

  @Column({
    type: DataType.STRING,
    allowNull: false,
  })
  status!: string;

  @Column({
    type: DataType.DATE,
    allowNull: false,
  })
  started_at!: Date;

  @Column({
    type: DataType.DATE,
    allowNull: true,
  })
  completed_at?: Date;

  @Column({
    type: DataType.TEXT,
    allowNull: true,
  })
  error_message?: string;
}