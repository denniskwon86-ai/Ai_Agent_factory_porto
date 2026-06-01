package com.example.inventory.dto;

import com.example.inventory.model.enums.OrderStatus;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.time.LocalDateTime;
import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class OrderDTO {
    private Long orderId;
    private LocalDateTime orderDate;

    @NotNull(message = "Order status cannot be null")
    private OrderStatus status;

    @NotEmpty(message = "Order must contain at least one item")
    @Valid
    private List<OrderItemDTO> orderItems;

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class OrderCreateRequest {
        @NotEmpty(message = "Order must contain at least one item")
        @Valid
        private List<OrderItemCreateRequest> orderItems;
    }

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class OrderUpdateRequest {
        @NotNull(message = "Order status cannot be null")
        private OrderStatus status;
    }
}