import { Request, Response, NextFunction } from 'express';
import { ZodError } from 'zod';

export const validate = (schema: any) => (req: Request, res: Response, next: NextFunction) => {
  try {
    schema.parse(req.body);
    next();
  } catch (error) {
    if (error instanceof ZodError) {
      return res.status(400).json({
        message: 'Validation error',
        errors: error.errors.map((err: any) => ({
          path: err.path.join('.'),
          message: err.message,
        })),
      });
    }
    next(error); // Pass other errors to the global error handler
  }
};