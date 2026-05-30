import { Model, DataTypes, Sequelize, Optional } from 'sequelize';

interface SessionAttributes {
  session_id: number;
  name: string;
  storage_path: string;
  compression: string;
  encryption: string;
  created_at: Date;
  updated_at: Date;
}

interface SessionCreationAttributes extends Optional<SessionAttributes, 'session_id' | 'created_at' | 'updated_at'> {}

class Session extends Model<SessionAttributes, SessionCreationAttributes> implements SessionAttributes {
  public session_id!: number;
  public name!: string;
  public storage_path!: string;
  public compression!: string;
  public encryption!: string;
  public created_at!: Date;
  public updated_at!: Date;

  public static initialize(sequelize: Sequelize) {
    Session.init({
      session_id: {
        type: DataTypes.INTEGER,
        autoIncrement: true,
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
        allowNull: false,
        defaultValue: DataTypes.NOW,
      },
      updated_at: {
        type: DataTypes.DATE,
        allowNull: false,
        defaultValue: DataTypes.NOW,
      },
    }, {
      sequelize,
      tableName: 'sessions',
      timestamps: true, // Sequelize will manage created_at and updated_at
    });
  }
}

export default Session;