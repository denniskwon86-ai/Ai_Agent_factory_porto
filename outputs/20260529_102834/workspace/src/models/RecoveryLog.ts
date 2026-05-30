import { Model, DataTypes, Sequelize, Optional } from 'sequelize';

interface RecoveryLogAttributes {
  log_id: number;
  session_id: number;
  item_path: string;
  action_type: string;
  status: string;
  started_at: Date;
  completed_at: Date | null;
  error_message: string | null;
}

interface RecoveryLogCreationAttributes extends Optional<RecoveryLogAttributes, 'log_id' | 'completed_at' | 'error_message'> {}

class RecoveryLog extends Model<RecoveryLogAttributes, RecoveryLogCreationAttributes> implements RecoveryLogAttributes {
  public log_id!: number;
  public session_id!: number;
  public item_path!: string;
  public action_type!: string;
  public status!: string;
  public started_at!: Date;
  public completed_at!: Date | null;
  public error_message!: string | null;

  public static initialize(sequelize: Sequelize) {
    RecoveryLog.init({
      log_id: {
        type: DataTypes.INTEGER,
        autoIncrement: true,
        primaryKey: true,
      },
      session_id: {
        type: DataTypes.INTEGER,
        allowNull: false,
        references: {
          model: 'sessions', // This is the table name
          key: 'session_id', // This is the column name in the referenced table
        }
      },
      item_path: {
        type: DataTypes.STRING,
        allowNull: false,
      },
      action_type: {
        type: DataTypes.STRING,
        allowNull: false,
      },
      status: {
        type: DataTypes.STRING,
        allowNull: false,
      },
      started_at: {
        type: DataTypes.DATE,
        allowNull: false,
        defaultValue: DataTypes.NOW,
      },
      completed_at: {
        type: DataTypes.DATE,
        allowNull: true,
      },
      error_message: {
        type: DataTypes.TEXT,
        allowNull: true,
      },
    }, {
      sequelize,
      tableName: 'recovery_logs',
      timestamps: false, // We manage timestamps manually or don't need them for this table
    });
  }
}

export default RecoveryLog;