package com.example.inventory.service;

import com.example.inventory.dto.MaterialDTO;
import com.example.inventory.exception.ResourceNotFoundException;
import com.example.inventory.model.Material;
import com.example.inventory.repository.MaterialRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
public class MaterialService {

    private final MaterialRepository materialRepository;

    public MaterialService(MaterialRepository materialRepository) {
        this.materialRepository = materialRepository;
    }

    @Transactional
    public MaterialDTO createMaterial(MaterialDTO materialDTO) {
        Material material = new Material();
        material.setName(materialDTO.getName());
        material.setDescription(materialDTO.getDescription());
        Material savedMaterial = materialRepository.save(material);
        return toDTO(savedMaterial);
    }

    @Transactional(readOnly = true)
    public List<MaterialDTO> getAllMaterials() {
        return materialRepository.findAll().stream()
                .map(this::toDTO)
                .collect(Collectors.toList());
    }

    @Transactional(readOnly = true)
    public MaterialDTO getMaterialById(Long id) {
        Material material = materialRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Material not found with id: " + id));
        return toDTO(material);
    }

    @Transactional
    public MaterialDTO updateMaterial(Long id, MaterialDTO materialDTO) {
        Material existingMaterial = materialRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Material not found with id: " + id));

        existingMaterial.setName(materialDTO.getName());
        existingMaterial.setDescription(materialDTO.getDescription());
        Material updatedMaterial = materialRepository.save(existingMaterial);
        return toDTO(updatedMaterial);
    }

    @Transactional
    public void deleteMaterial(Long id) {
        if (!materialRepository.existsById(id)) {
            throw new ResourceNotFoundException("Material not found with id: " + id);
        }
        materialRepository.deleteById(id);
    }

    private MaterialDTO toDTO(Material material) {
        return new MaterialDTO(material.getMaterialId(), material.getName(), material.getDescription());
    }
}