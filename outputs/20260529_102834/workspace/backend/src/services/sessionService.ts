import { Op } from 'sequelize';
import Session from '../models/Session';
import SessionItem from '../models/SessionItem';
import RecoveryLog from '../models/RecoveryLog';
import { CreateSessionInput, UpdateSessionInput, CreateSessionWithItemsInput, CreateRecoveryLogInput } from '../schemas/session';

export class SessionService {
  async createSession(data: CreateSessionInput): Promise<Session> {
    return Session.create(data);
  }

  async getAllSessions(): Promise<Session[]> {
    return Session.findAll();
  }

  async getSessionById(sessionId: number): Promise<Session | null> {
    return Session.findByPk(sessionId, {
      include: [SessionItem, RecoveryLog],
    });
  }

  async updateSession(sessionId: number, data: UpdateSessionInput): Promise<Session | null> {
    const session = await Session.findByPk(sessionId);
    if (!session) {
      return null;
    }
    return session.update(data);
  }

  async deleteSession(sessionId: number): Promise<boolean> {
    const deletedRows = await Session.destroy({ where: { session_id: sessionId } });
    return deletedRows > 0;
  }

  async addSessionItems(sessionId: number, items: CreateSessionWithItemsInput['items']): Promise<SessionItem[]> {
    if (!items || items.length === 0) {
      return [];
    }
    const sessionItemsData = items.map(item => ({ ...item, session_id: sessionId }));
    return SessionItem.bulkCreate(sessionItemsData);
  }

  async getSessionItems(sessionId: number): Promise<SessionItem[]> {
    return SessionItem.findAll({ where: { session_id: sessionId } });
  }

  async createRecoveryLog(sessionId: number, data: CreateRecoveryLogInput): Promise<RecoveryLog> {
    return RecoveryLog.create({ ...data, session_id: sessionId });
  }

  async getRecoveryLogs(sessionId: number): Promise<RecoveryLog[]> {
    return RecoveryLog.findAll({ where: { session_id: sessionId } });
  }
}