import { Sequelize, DataTypes, Model } from 'sequelize';

interface RecoveryLogAttributes {
  log_id: string;
  session_id: string;
  item_path: string;
  action_type: string;
  status: string;
  started_at: Date;
  completed_at: Date | null;
  error_message: string | null;
}

export default (sequelize: Sequelize) => {
  class RecoveryLog extends Model<RecoveryLogAttributes> implements RecoveryLogAttributes {
    public log_id!: string;
    public session_id!: string;
    public item_path!: string;
    public action_type!: string;
    public status!: string;
    public started_at!: Date;
    public completed_at!: Date | null;
    public error_message!: string | null;

    static associate(models: any) {
      // define association here
    }
  }

  RecoveryLog.init({
    log_id: {
      type: DataTypes.UUID,
      defaultValue: DataTypes.UUIDV4,
      primaryKey: true,
    },
    session_id: {
      type: DataTypes.UUID,
      allowNull: false,
      references: {
        model: 'sessions',
        key: 'session_id',
      },
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
    modelName: 'RecoveryLog',
    tableName: 'recovery_logs',
    timestamps: false, // No timestamps for this table as per schema
  });

  return RecoveryLog;
};