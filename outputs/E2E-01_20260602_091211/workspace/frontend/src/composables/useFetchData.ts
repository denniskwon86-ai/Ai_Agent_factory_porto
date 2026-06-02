import { ref, onMounted } from 'vue';

/**
 * A Vue 3 composable (custom hook) for fetching data from an asynchronous source.
 * It manages loading and error states.
 *
 * @param fetcher An asynchronous function that returns the data.
 * @returns An object containing `data`, `loading`, and `error` refs.
 */
export function useFetchData<T>(fetcher: () => Promise<T>) {
  const data = ref<T | null>(null);
  const loading = ref(true);
  const error = ref<string | null>(null);

  onMounted(async () => {
    try {
      data.value = await fetcher();
    } catch (e: any) {
      error.value = `Failed to load data: ${e.message}`;
      console.error("Error fetching data:", e);
    } finally {
      loading.value = false;
    }
  });

  return { data, loading, error };
}
</