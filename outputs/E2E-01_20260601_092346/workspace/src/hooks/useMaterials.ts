import { useState, useEffect, useCallback } from 'react';
    import { Material, MaterialPagination, getMaterials, deleteMaterial, createMaterial, updateMaterial } from '../services/materialService';

    interface UseMaterialsResult {
      materials: Material[];
      loading: boolean;
      error: string | null;
      pagination: MaterialPagination;
      loadMaterials: (page?: number, size?: number) => Promise<void>;
      addMaterial: (material: Omit<Material, 'materialId' | 'status'>) => Promise<void>;
      editMaterial: (id: number, material: Partial<Material>) => Promise<void>;
      deleteExistingMaterial: (id: number) => Promise<void>;
    }

    export const useMaterials = (): UseMaterialsResult => {
      const [materials, setMaterials] = useState<Material[]>([]);
      const [loading, setLoading] = useState<boolean>(true);
      const [error, setError] = useState<string | null>(null);
      const [pagination, setPagination] = useState<MaterialPagination>({
        pageNumber: 0,
        pageSize: 10,
        totalPages: 0,
        totalElements: 0,
      });

      const loadMaterials = useCallback(async (page: number = 0, size: number = 10) => {
        setLoading(true);
        setError(null);
        try {
          const response = await getMaterials(page, size);
          setMaterials(response.content);
          setPagination({
            pageNumber: response.pageable.pageNumber,
            pageSize: response.pageable.pageSize,
            totalPages: response.pageable.totalPages,
            totalElements: response.pageable.totalElements,
          });
        } catch (err: any) {
          setError(err.message || 'Failed to load materials.');
        } finally {
          setLoading(false);
        }
      }, []);

      const addMaterial = useCallback(async (material: Omit<Material, 'materialId' | 'status'>) => {
        try {
          await createMaterial(material);
          loadMaterials(pagination.pageNumber, pagination.pageSize); // Reload current page
        } catch (err: any) {
          setError(err.message || 'Failed to add material.');
          throw err; // Re-throw to allow component to handle UI feedback
        }
      }, [loadMaterials, pagination.pageNumber, pagination.pageSize]);

      const editMaterial = useCallback(async (id: number, material: Partial<Material>) => {
        try {
          await updateMaterial(id, material);
          setMaterials(prevMaterials =>
            prevMaterials.map(m =>
              m.materialId === id ? { ...m, ...material } : m
            )
          );
          // Optionally reload the page if status or other critical fields changed that affect list view
          // loadMaterials(pagination.pageNumber, pagination.pageSize);
        } catch (err: any) {
          setError(err.message || 'Failed to update material.');
          throw err;
        }
      }, [loadMaterials, pagination.pageNumber, pagination.pageSize]);

      const deleteExistingMaterial = useCallback(async (id: number) => {
        try {
          await deleteMaterial(id);
          setMaterials(prevMaterials => prevMaterials.filter(m => m.materialId !== id));
          // Adjust pagination if the last item on the page was deleted
          if (materials.length === 1 && pagination.pageNumber > 0) {
            loadMaterials(pagination.pageNumber - 1, pagination.pageSize);
          } else {
            loadMaterials(pagination.pageNumber, pagination.pageSize);
          }
        } catch (err: any) {
          setError(err.message || 'Failed to delete material.');
          throw err;
        }
      }, [materials.length, loadMaterials, pagination.pageNumber, pagination.pageSize]);

      useEffect(() => {
        loadMaterials();
      }, [loadMaterials]);

      return {
        materials,
        loading,
        error,
        pagination,
        loadMaterials,
        addMaterial,
        editMaterial,
        deleteExistingMaterial,
      };
    };