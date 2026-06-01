// This file is a placeholder for Redux Toolkit store configuration.
    // If you are not using Redux for global state management, you can remove this file
    // and the Provider wrapper in main.tsx.
    // For now, we'll create a minimal store.

    import { configureStore } from '@reduxjs/toolkit';

    export const store = configureStore({
      reducer: {
        // Add your reducers here
        // exampleReducer: exampleSlice.reducer,
      },
    });

    // Infer the `RootState` and `AppDispatch` types from the store itself
    export type RootState = ReturnType<typeof store.getState>;
    // Inferred type: {posts: PostsState, comments: CommentsState, users: UsersState}
    export type AppDispatch = typeof store.dispatch;