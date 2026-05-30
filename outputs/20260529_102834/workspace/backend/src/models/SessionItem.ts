import { Table, Column, Model, DataType, ForeignKey } from 'sequelize-typescript';
import Session from './Session';

@Table({ tableName: 'session_items', timestamps: false })
export default class SessionItem extends Model {
  @Column({
    type: DataType.INTEGER,
    autoIncrement: true,
    primaryKey: true,
  })
  session_item_id!: number;

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
  item_type!: string;
}