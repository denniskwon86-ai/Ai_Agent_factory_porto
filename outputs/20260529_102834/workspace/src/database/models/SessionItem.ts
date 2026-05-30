import { Sequelize, DataTypes, Model } from 'sequelize';

interface SessionItemAttributes {
  session_item_id: string;
  session_id: string;
  item_path: string;
  item_type: string;
}

export default (sequelize: Sequelize) => {
  class SessionItem extends Model<SessionItemAttributes> implements SessionItemAttributes {
    public session_item_id!: string;
    public session_id!: string;
    public item_path!: string;
    public item_type!: string;

    static associate(models: any) {
      // define association here
    }
  }

  SessionItem.init({
    session_item_id: {
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
    item_type: {
      type: DataTypes.STRING,
      allowNull: false,
    },
  }, {
    sequelize,
    modelName: 'SessionItem',
    tableName: 'session_items',
    timestamps: false, // No timestamps for this table as per schema
  });

  return SessionItem;
};