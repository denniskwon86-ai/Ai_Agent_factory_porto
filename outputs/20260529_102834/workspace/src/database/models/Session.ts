import { Sequelize, DataTypes, Model } from 'sequelize';

interface SessionAttributes {
  session_id: string;
  name: string;
  storage_path: string;
  compression: string;
  encryption: string;
  created_at: Date;
  updated_at: Date;
}

export default (sequelize: Sequelize) => {
  class Session extends Model<SessionAttributes> implements SessionAttributes {
    public session_id!: string;
    public name!: string;
    public storage_path!: string;
    public compression!: string;
    public encryption!: string;
    public created_at!: Date;
    public updated_at!: Date;

    static associate(models: any) {
      // define association here
    }
  }

  Session.init({
    session_id: {
      type: DataTypes.UUID,
      defaultValue: DataTypes.UUIDV4,
      primaryKey: true,
    },
    name: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    storage_path: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    compression: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    encryption: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    created_at: {
      type: DataTypes.DATE,
      defaultValue: DataTypes.NOW,
    },
    updated_at: {
      type: DataTypes.DATE,
      defaultValue: DataTypes.NOW,
    },
  }, {
    sequelize,
    modelName: 'Session',
    tableName: 'sessions',
    timestamps: true,
  });

  return Session;
};