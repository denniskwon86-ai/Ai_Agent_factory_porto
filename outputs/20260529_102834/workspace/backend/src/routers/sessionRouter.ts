import { Router, Request, Response, NextFunction } from 'express';
import { SessionService } from '../services/sessionService';
import {
  createSessionSchema,
  updateSessionSchema,
  createSessionWithItemsSchema,
  createRecoveryLogSchema,
} from '../schemas/session';
import { validate } from '../middleware/validationMiddleware';
import { z } from 'zod';

const router = Router();
const sessionService = new SessionService();

// POST /sessions
router.post(
  '/sessions',
  validate(createSessionWithItemsSchema),
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { items, ...sessionData } = req.body;
      const session = await sessionService.createSession(sessionData);
      if (items && items.length > 0) {
        await sessionService.addSessionItems(session.session_id, items);
      }
      const createdSession = await sessionService.getSessionById(session.session_id);
      res.status(201).json(createdSession);
    } catch (error) {
      next(error);
    }
  }
);

// GET /sessions
router.get('/sessions', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const sessions = await sessionService.getAllSessions();
    res.status(200).json(sessions);
  } catch (error) {
    next(error);
  }
});

// GET /sessions/:id
router.get('/sessions/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const sessionId = parseInt(req.params.id, 10);
    const session = await sessionService.getSessionById(sessionId);
    if (!session) {
      return res.status(404).json({ message: 'Session not found' });
    }
    res.status(200).json(session);
  } catch (error) {
    next(error);
  }
});

// PUT /sessions/:id
router.put(
  '/sessions/:id',
  validate(updateSessionSchema),
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const sessionId = parseInt(req.params.id, 10);
      const session = await sessionService.updateSession(sessionId, req.body);
      if (!session) {
        return res.status(404).json({ message: 'Session not found' });
      }
      res.status(200).json(session);
    } catch (error) {
      next(error);
    }
  }
);

// DELETE /sessions/:id
router.delete('/sessions/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const sessionId = parseInt(req.params.id, 10);
    const deleted = await sessionService.deleteSession(sessionId);
    if (!deleted) {
      return res.status(404).json({ message: 'Session not found' });
    }
    res.status(204).send();
  } catch (error) {
    next(error);
  }
});

// POST /sessions/:id/items
router.post(
  '/sessions/:id/items',
  validate(z.object({ items: z.array(createSessionSchema.pick({ name: true, storage_path: true, compression: true, encryption: true })) })), // Simplified schema for items
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const sessionId = parseInt(req.params.id, 10);
      const { items } = req.body;
      const createdItems = await sessionService.addSessionItems(sessionId, items);
      res.status(201).json(createdItems);
    } catch (error) {
      next(error);
    }
  }
);

// GET /sessions/:id/items
router.get('/sessions/:id/items', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const sessionId = parseInt(req.params.id, 10);
    const items = await sessionService.getSessionItems(sessionId);
    res.status(200).json(items);
  } catch (error) {
    next(error);
  }
});

// POST /sessions/:id/recovery-logs
router.post(
  '/sessions/:id/recovery-logs',
  validate(createRecoveryLogSchema),
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const sessionId = parseInt(req.params.id, 10);
      const logData = req.body;
      const recoveryLog = await sessionService.createRecoveryLog(sessionId, logData);
      res.status(201).json(recoveryLog);
    } catch (error) {
      next(error);
    }
  }
);

// GET /sessions/:id/recovery-logs
router.get('/sessions/:id/recovery-logs', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const sessionId = parseInt(req.params.id, 10);
    const logs = await sessionService.getRecoveryLogs(sessionId);
    res.status(200).json(logs);
  } catch (error) {
    next(error);
  }
});

export default router;