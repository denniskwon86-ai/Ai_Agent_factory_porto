import { Model, DataTypes, Sequelize, Optional } from 'sequelize';

interface SessionItemAttributes {
  session_item_id: number;
  session_id: number;
  item_path: string;
  item_type: string;
}

interface SessionItemCreationAttributes extends Optional<SessionItemAttributes, 'session_item_id'> {}

class SessionItem extends Model<SessionItemAttributes, SessionItemCreationAttributes> implements SessionItemAttributes {
  public session_item_id!: number;
  public session_id!: number;
  public item_path!: string;
  public item_type!: string;

  public static initialize(sequelize: Sequelize) {
    SessionItem.init({
      session_item_id: {
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
      item_type: {
        type: DataTypes.STRING,
        allowNull: false, // e.g., 'file', 'directory'
      },
    }, {
      sequelize,
      tableName: 'session_items',
      timestamps: false, // No timestamps needed for this table
    });
  }
}

export default SessionItem;