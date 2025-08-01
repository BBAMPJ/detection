import sys
import cv2
import torch
import numpy as np
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import qtawesome as qta
import time
import math

class NavBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.vision_status = "Standby"

    def setVisionStatus(self, status: str):
        self.vision_status = status
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        reference_width = 1200
        scale = min(w / reference_width, 1.0)

        # Responsive parameters
        margin_top = 30 * scale
        trap_height = 50 * scale
        max_trap_width = 250 * scale
        max_bottom_offset = 30 * scale
        slope_width = 30 * scale
        pen_width = max(2, int(3 * scale))

        trap_width = max_trap_width
        bottom_offset = max_bottom_offset
        center_x = w / 2

        # Gradient background
        gradient = QLinearGradient(0, 0, 0, margin_top + trap_height)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 200))
        gradient.setColorAt(0.5, QColor(200, 200, 200, 0))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(0, 0, w, margin_top + trap_height))

        # Main trapezoid polygon
        points = QPolygonF([
            QPointF(center_x - trap_width / 2, margin_top),
            QPointF(center_x + trap_width / 2, margin_top),
            QPointF(center_x + trap_width / 2 - bottom_offset, margin_top + trap_height),
            QPointF(center_x - trap_width / 2 + bottom_offset, margin_top + trap_height),
        ])

        painter.setBrush(QColor(100, 100, 100, 150))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(points)

        # Border of trapezoid
        pen = QPen(QColor("white"))
        pen.setWidth(pen_width)
        painter.setPen(pen)
        painter.drawPolygon(points)

        # NavBar side borders
        flat_length = (w - (trap_width + 2 * slope_width)) / 2

        painter.drawLine(QPointF(0, margin_top),
                         QPointF(flat_length, margin_top))
        painter.drawLine(QPointF(flat_length, margin_top),
                         QPointF(flat_length + slope_width, margin_top + trap_height))
        painter.drawLine(QPointF(w - flat_length - slope_width, margin_top + trap_height),
                         QPointF(w - flat_length, margin_top))
        painter.drawLine(QPointF(w - flat_length, margin_top),
                         QPointF(w, margin_top))

        # Fonts
        status_font_size = max(8, int(12 * scale))
        label_font_size = max(6, int(10 * scale))

        status_font = QFont("sans-serif", status_font_size)
        label_font = QFont("sans-serif", label_font_size)

        # Text rects
        rect = points.boundingRect()
        status_rect = QRectF(rect)
        status_rect.setTop(rect.top() + 5 * scale)

        label_rect = QRectF(rect)
        label_rect.setBottom(rect.bottom() - 5 * scale)

        # Draw vision status
        painter.setFont(status_font)
        painter.setPen(QColor("orange"))
        painter.drawText(status_rect, Qt.AlignTop | Qt.AlignHCenter, self.vision_status)

        # Draw "vision"
        painter.setFont(label_font)
        painter.setPen(QColor("white"))
        painter.drawText(label_rect, Qt.AlignBottom | Qt.AlignHCenter, "vision")


class HudOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.heading_deg = 0
        self.pitch_deg = 0
        self.zoom_level = 0.5     
        self.focus_level = 0.5     
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_heading(self, heading_deg):
        self.heading_deg = heading_deg % 360
        self.update()

    def set_zoom_level(self, zoom):
        self.zoom_level = max(0.0, min(1.0, zoom))        
        self.update() 

    def set_pitch(self, pitch_deg):
        self.pitch_deg = max(-90, min(90, pitch_deg))
        print(f"[HUD] Updated pitch: {self.pitch_deg}")
        self.update()

    def auto_adjust_zoom_focus_from_bbox(self, bbox_width, bbox_height, frame_width, frame_height):
        print("auto_adjust_zoom_focus_from_bbox called")
        object_area = bbox_width * bbox_height
        frame_area = frame_width * frame_height
        object_ratio = object_area / frame_area

        print(f"[DEBUG] bbox: {bbox_width}x{bbox_height}, frame: {frame_width}x{frame_height}, ratio: {object_ratio:.4f}, zoom_level before: {self.zoom_level:.4f}")

         # Adjust the range to balance: far → middle → near
        min_ratio = 0.0005  # left
        max_ratio = 0.0093  # right ( 0.0049 center)

        if object_ratio < min_ratio:
            self.zoom_level = 0.0
            self.focus_level = 0.0
            print("Condition: object_ratio < min_ratio")
        elif object_ratio > max_ratio:
            self.zoom_level = 1.0
            self.focus_level = 1.0
            # print("Condition: object_ratio > max_ratio")
        else:
            normalized = (object_ratio - min_ratio) / (max_ratio - min_ratio)
            self.zoom_level = normalized
            self.focus_level = normalized
            # print("Condition: object_ratio in between")

        # print(f"[DEBUG] zoom_level after: {self.zoom_level:.4f}, focus_level: {self.focus_level:.4f}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        ref_w, ref_h = 1920, 1080
        scale = min(w / ref_w, h / ref_h)

        self.draw_horizontal_scale(painter, w, h, scale)
        self.draw_vertical_scale(painter, w, h, scale)
        self.draw_compass(painter, int(450 * scale), h - int(150 * scale), int(200 * scale), scale)
        self.draw_pitch_gauge(painter, int(150 * scale), h - int(150 * scale), int(200 * scale), scale)

        focus_y, bg_x, bg_width = self.draw_zoom_control(painter, scale, self.zoom_level)
        self.draw_focus_control(painter, scale, focus_y, bg_x, bg_width)

        # Crosshair
        self.draw_crosshair(painter, w, h, scale)

    def draw_crosshair(self, painter, w, h, scale):
        cx, cy = w // 2, h // 2

        bar_length = int(250 * scale)
        bar_thickness = int(4 * scale)
        gap = int(60 * scale)  

        painter.setRenderHint(QPainter.Antialiasing)

        pen = QPen(QColor(255, 255, 255))
        pen.setWidthF(1.0)  
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        # left
        left_rect = QRect(cx - gap - bar_length, cy - bar_thickness // 2, bar_length, bar_thickness)
        painter.drawRect(left_rect)

        # right
        right_rect = QRect(cx + gap, cy - bar_thickness // 2, bar_length, bar_thickness)
        painter.drawRect(right_rect)

        # top
        top_rect = QRect(cx - bar_thickness // 2, cy - gap - bar_length, bar_thickness, bar_length)
        painter.drawRect(top_rect)

        # bottom
        bottom_rect = QRect(cx - bar_thickness // 2, cy + gap, bar_thickness, bar_length)
        painter.drawRect(bottom_rect)


    def draw_zoom_control(self, painter, scale, zoom_level):
        margin = 50 * scale
        width = 200 * scale
        height = 70 * scale

        x = self.width() - width - margin
        y = self.height() - height - margin - (70 * scale)

        big_width = 45 * scale
        big_height = 70 * scale
        small_scale = 0.7
        small_offset = 4 * scale
        small_side_scale = 0.7

        gap_from_mountain = 20 * scale
        line_length = 180 * scale
        padding_vertical = 15 * scale
        tick_height = 10 * scale

        actual_heights = [
            big_height,
            big_height * small_scale - 3 * scale,
            big_height * small_side_scale,
            big_height * small_side_scale * small_scale - 3 * scale * small_side_scale
        ]
        max_actual_height = max(actual_heights)
        
        bg_height = max_actual_height + 2 * padding_vertical
        base_y = y + height - bg_height + padding_vertical + max_actual_height
        line_y = base_y - 15 * scale
        bg_y = line_y - bg_height / 2

        center_x_right = x + width - margin - big_width / 2 - gap_from_mountain
        line_x2 = center_x_right - big_width / 2 - gap_from_mountain
        line_x1 = line_x2 - line_length
        
        small_center_x_left = line_x1 - gap_from_mountain - (big_width * small_side_scale * small_scale) / 2
        center_x_left = small_center_x_left - (big_width * small_side_scale / 2 + small_offset * small_side_scale)
        small_center_x_right = center_x_right + (big_width / 2 + small_offset)

        painter.save()

        # Calculate background position
        extra_width = 30 * scale
        bg_x = small_center_x_left - (big_width * small_side_scale * small_scale) / 2 - margin - extra_width / 2
        bg_width = center_x_right + big_width / 2 + margin + extra_width / 2 - bg_x

        painter.setBrush(QColor(60, 60, 60, 200))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(bg_x, bg_y, bg_width, bg_height), 12 * scale, 12 * scale)

        # line
        painter.setPen(QPen(QColor(200, 200, 200), 1.5))
        painter.drawLine(QPointF(line_x1, line_y), QPointF(line_x2, line_y))
        for x_pos in [line_x1, line_x2]:
            painter.drawLine(QPointF(x_pos, line_y - tick_height / 2),
                            QPointF(x_pos, line_y + tick_height / 2))

        zoom_level = getattr(self, "zoom_level", 0.5)
        handle_x = line_x1 + zoom_level * (line_x2 - line_x1)
        painter.setPen(QPen(QColor(255, 204, 0), 4))
        painter.drawLine(QPointF(handle_x, line_y - tick_height),
                        QPointF(handle_x, line_y + tick_height))

        def draw_mountain(center_x, width, height, offset=0):
            path = QPainterPath()
            path.moveTo(center_x - width / 2, base_y)
            path.quadTo(center_x, base_y - height + offset, center_x + width / 2, base_y)
            path.lineTo(center_x - width / 2, base_y)
            
            painter.setBrush(QColor(255, 255, 255))
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)
            
            if width == big_width or width == big_width * small_side_scale:
                painter.setPen(QPen(QColor(0, 0, 0, 100), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)

        mountains = [
            (small_center_x_right, big_width * small_scale, big_height * small_scale, 3 * scale),
            (center_x_right, big_width, big_height, -10 * scale),
            (small_center_x_left, big_width * small_side_scale * small_scale,
            big_height * small_side_scale * small_scale, 3 * scale * small_side_scale),
            (center_x_left, big_width * small_side_scale, big_height * small_side_scale,
            -10 * scale * small_side_scale)
        ]

        for center_x, width, height, offset in mountains:
            draw_mountain(center_x, width, height, offset)

        painter.restore()
        return bg_y + bg_height + 10 * scale, bg_x, bg_width

    def draw_focus_control(self, painter, scale, y, bg_x, bg_width):
        height = 40 * scale
        x = bg_x
        width = bg_width

        # background
        radius = 8 * scale
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(60, 60, 60, 160))
        painter.drawRoundedRect(QRectF(x, y, width, height), radius, radius)

        # icon len
        lens_outer_r = 12 * scale
        lens_middle_r = 8 * scale
        lens_inner_r = 3 * scale
        lens_x = x + 25 * scale
        lens_y = y + height / 2

        painter.setBrush(QColor(255, 255, 255, 200))
        painter.drawEllipse(QRectF(lens_x - lens_outer_r, lens_y - lens_outer_r, 
                                2 * lens_outer_r, 2 * lens_outer_r))
        painter.setBrush(QColor(80, 80, 80))
        painter.drawEllipse(QRectF(lens_x - lens_middle_r, lens_y - lens_middle_r, 
                                2 * lens_middle_r, 2 * lens_middle_r))
        painter.setBrush(QColor(120, 120, 120))
        painter.drawEllipse(QRectF(lens_x - lens_inner_r, lens_y - lens_inner_r, 
                                2 * lens_inner_r, 2 * lens_inner_r))

        # distance
        distances = [20, 40, 100, 300, 800, 2000]
        slider_start = x + 50 * scale
        slider_width = width - 70 * scale
        step = slider_width / (len(distances) - 1)

        tick_height = 7 * scale
        tick_offset_y = 15 * scale
        text_offset_y = 5 * scale

        painter.setPen(QColor(200, 200, 200))
        font = QFont("sans-serif", max(1, int(8 * scale)))
        painter.setFont(font)

        for i, dist in enumerate(distances):
            line_x = slider_start + i * step
            painter.drawLine(QPointF(line_x, y + height - tick_offset_y),
                            QPointF(line_x, y + height - (tick_offset_y - tick_height)))

            label = str(dist)
            text_rect = painter.boundingRect(
                QRectF(line_x - 20 * scale, y + text_offset_y, 40 * scale, 15 * scale),
                Qt.AlignCenter, label
            )
            painter.drawText(text_rect, Qt.AlignCenter, label)

        # line slider main
        painter.setPen(QPen(QColor(180, 180, 180), 2))
        slider_y = y + height - 12 * scale
        painter.drawLine(QPointF(slider_start, slider_y),
                        QPointF(slider_start + slider_width, slider_y))

        # handle
        handle_x = slider_start + self.focus_level * slider_width
        handle_r = 6 * scale

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 204, 0))
        painter.drawEllipse(QRectF(handle_x - handle_r, slider_y - handle_r,
                                2 * handle_r, 2 * handle_r))

        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(handle_x - handle_r, slider_y - handle_r,
                                2 * handle_r, 2 * handle_r))
        
    # scale axis X
    def draw_horizontal_scale(self, painter, w, h, scale):
        center_x = w // 2
        bar_y = int(h - 60 * scale)

        bg_color = QColor(60, 60, 60, 200)
        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        scale_length_px = int(800 * scale)
        rect_x = center_x - scale_length_px // 2 - int(10 * scale)
        rect_y = bar_y - int(40 * scale)
        rect_w = scale_length_px + int(20 * scale)
        rect_h = int(80 * scale)
        corner_radius = int(15 * scale)
        painter.drawRoundedRect(rect_x, rect_y, rect_w, rect_h, corner_radius, corner_radius)

        deg_per_px = 4 / scale
        visible_deg = int(scale_length_px / deg_per_px)
        start_deg = int((self.heading_deg - visible_deg // 2) // 10 * 10)

        tick_height_small = int(8 * scale)
        tick_height_large = int(14 * scale)
        text_y_offset = int(18 * scale)

        tick_color = QColor(255, 255, 255)

        pen_tick = QPen(tick_color)
        pen_tick.setWidth(1)
        painter.setPen(pen_tick)
        font = QFont("sans-serif", max(1, int(8 * scale)))
        painter.setFont(font)

        painter.save()
        painter.setClipRect(QRect(rect_x, rect_y, rect_w, rect_h))

        for deg_tick in range(start_deg, start_deg + visible_deg + 10, 5):
            deg_mod = deg_tick % 360
            px_offset = (deg_tick - self.heading_deg) * deg_per_px
            x = int(center_x + px_offset)

            if rect_x <= x <= rect_x + rect_w:
                if deg_tick % 10 == 0:
                    painter.drawLine(x, bar_y - tick_height_large, x, bar_y)
                    label = str(deg_mod)
                    text_rect = painter.boundingRect(x - int(15 * scale),
                                                    bar_y + text_y_offset - int(10 * scale),
                                                    int(30 * scale), int(20 * scale),
                                                    Qt.AlignCenter, label)
                    painter.drawText(text_rect, Qt.AlignCenter, label)
                else:
                    painter.drawLine(x, bar_y - tick_height_small, x, bar_y)
        painter.restore()

        triangle_height = int(20 * 1.5 * scale)
        triangle_width = int(24 * 1.5 * scale)
        offset_y = int(10 * scale)

        tip = QPoint(center_x, bar_y - int(40 * scale) + offset_y)
        left = QPoint(center_x - triangle_width // 2, bar_y - int(40 * scale) - triangle_height + offset_y)
        right = QPoint(center_x + triangle_width // 2, bar_y - int(40 * scale) - triangle_height + offset_y)
        triangle = QPolygon([tip, left, right])

        triangle_color = QColor(199, 153, 0)
        triangle_border = QColor(60, 60, 60)

        painter.setBrush(triangle_color)
        painter.setPen(QPen(triangle_border, 1))
        painter.drawPolygon(triangle)

        painter.setPen(QColor(255, 255, 255))
        font2 = QFont("sans-serif", max(1, int(9 * scale)), QFont.Bold)
        painter.setFont(font2)
        label = str(int(self.heading_deg))
        text_rect = painter.boundingRect(center_x - int(20 * scale),
                                        tip.y() - int(60 * scale),
                                        int(40 * scale), int(20 * scale),
                                        Qt.AlignCenter, label)
        painter.drawText(text_rect, Qt.AlignCenter, label)

    # scale axis Y
    def draw_vertical_scale(self, painter, w, h, scale):
        bar_x = w - int(100 * scale)
        center_y = h // 2

        scale_length_px = int(600 * scale)
        visible_deg = 180
        deg_per_px = visible_deg / scale_length_px

        tick_interval = 10
        tick_length = int(15 * scale)
        axis_line_width = 2

        pen_axis = QPen(QColor(200, 200, 200))
        pen_axis.setWidth(axis_line_width)
        painter.setPen(pen_axis)
        painter.drawLine(bar_x, center_y - scale_length_px // 2,
                        bar_x, center_y + scale_length_px // 2)

        pen_tick = QPen(QColor(255, 255, 255))
        pen_tick.setWidth(1)
        painter.setPen(pen_tick)
        font = QFont("sans-serif", max(1, int(8 * scale)))
        painter.setFont(font)

        for deg_tick in range(-90, 91, tick_interval):
            px_offset = int((90 - deg_tick) / deg_per_px)
            y = center_y - scale_length_px // 2 + px_offset

            painter.drawLine(bar_x, y, bar_x + tick_length, y)

            if deg_tick in [-90, 0, 90]:
                label = str(deg_tick)
                text_rect = painter.boundingRect(
                    bar_x + tick_length + int(5 * scale),
                    y - int(10 * scale),
                    int(25 * scale),
                    int(20 * scale),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    label
                )
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, label)

        triangle_height = int(20 * scale)
        triangle_width = int(24 * scale)

        tip_y = center_y - scale_length_px // 2 + int((90 - self.pitch_deg) / deg_per_px)
        offset_x = int(35 * scale)

        tip = QPoint(bar_x + tick_length + triangle_width - offset_x, tip_y)
        left = QPoint(bar_x + tick_length - offset_x, tip_y - triangle_height // 2)
        right = QPoint(bar_x + tick_length - offset_x, tip_y + triangle_height // 2)

        triangle = QPolygon([tip, left, right])

        triangle_color = QColor(199, 153, 0)
        triangle_border = QColor(60, 60, 60)

        painter.setBrush(triangle_color)
        painter.setPen(QPen(triangle_border, 1))
        painter.drawPolygon(triangle)

        label = str(int(self.pitch_deg))
        text_x = tip.x() - int(60 * scale)
        text_y = tip.y() - int(10 * scale)

        text_rect = painter.boundingRect(
            text_x, text_y, int(30 * scale), int(20 * scale),
            Qt.AlignRight | Qt.AlignVCenter, label
        )
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter, label)
    
    # scale compass X
    def draw_compass(self, painter, center_x, center_y, diameter, scale):
        radius = diameter // 2
        center = QPoint(center_x, center_y)

        # Outer circle
        painter.setBrush(QColor(50, 50, 50, 220))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, radius, radius)

        # Inner circle
        inner_radius = int(radius * 0.75)  
        pen_inner = QPen(QColor(255, 255, 255, 150))
        pen_inner.setWidth(max(1, int(2 * scale)))
        painter.setPen(pen_inner)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, inner_radius, inner_radius)

        # Direction labels: N, E, W
        directions = {
            'N': 0,
            'E': 90,
            'W': 270,
        }
        font = QFont("sans-serif", max(1, int(8 * scale))) 
        painter.setFont(font)
        painter.setPen(QColor("white"))

        label_radius = inner_radius + int(15 * scale) 
        for label, angle_deg in directions.items():
            angle_rad = math.radians(angle_deg)
            x = center.x() + label_radius * math.sin(angle_rad)
            y = center.y() - label_radius * math.cos(angle_rad)
            text_size = int(24 * scale) 
            text_rect = QRectF(x - text_size / 2, y - text_size / 2, text_size, text_size)
            painter.drawText(text_rect, Qt.AlignCenter, label)

        # Compass needle
        angle_rad = math.radians(self.heading_deg)
        needle_length = inner_radius
        needle_width = max(int(radius * 0.1), 3)

        tip_x = center.x() + needle_length * math.sin(angle_rad)
        tip_y = center.y() - needle_length * math.cos(angle_rad)

        base_left_x = center.x() + (needle_width / 2) * math.cos(angle_rad)
        base_left_y = center.y() + (needle_width / 2) * math.sin(angle_rad)

        base_right_x = center.x() - (needle_width / 2) * math.cos(angle_rad)
        base_right_y = center.y() - (needle_width / 2) * math.sin(angle_rad)

        needle_polygon = QPolygon([
            QPoint(int(tip_x), int(tip_y)),
            QPoint(int(base_left_x), int(base_left_y)),
            QPoint(int(base_right_x), int(base_right_y)),
        ])

        painter.setBrush(QColor(255, 165, 0)) 
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(needle_polygon)

        # Needle center dot
        painter.setBrush(QColor(255, 165, 0))
        painter.drawEllipse(center, needle_width // 2, needle_width // 2)

        # Degree number below compass
        degree_text = f"{int(self.heading_deg)}°"
        font_num = QFont("sans-serif", max(1, int(8 * scale)))
        painter.setFont(font_num)
        painter.setPen(QColor("white"))

        text_height = int(24 * scale)
        text_rect = QRectF(center.x() - radius, center.y() + radius - text_height, radius * 2, text_height)
        painter.drawText(text_rect, Qt.AlignCenter, degree_text)

    # compass Y
    def draw_pitch_gauge(self, painter, center_x, center_y, diameter, scale):
        radius = diameter // 2
        center = QPoint(center_x, center_y)
        offset = int(20 * scale)
        clip_rect = QRectF(center_x - offset, center_y - radius, radius + offset, diameter)

        # CLIP right circle indented left
        painter.save()
        painter.setClipRect(clip_rect)

        painter.setBrush(QColor(50, 50, 50, 220))
        painter.setPen(Qt.NoPen)
        circle_rect = QRectF(center_x - radius, center_y - radius, diameter, diameter)
        painter.drawEllipse(circle_rect)

        painter.restore()

        # Inner Circle
        inner_radius = int(radius * 0.75)  
        pen_inner = QPen(QColor(255, 255, 255, 100))
        pen_inner.setWidth(max(1, int(2 * scale)))
        painter.setPen(pen_inner)
        painter.setBrush(Qt.NoBrush)

        painter.save()
        painter.setClipRect(clip_rect)
        inner_rect = QRectF(center_x - inner_radius, center_y - inner_radius, inner_radius * 2, inner_radius * 2)
        painter.drawArc(inner_rect, 0, 360 * 16)
        painter.restore()
        
        # Horizontal line (0°)
        pen_axis = QPen(QColor(255, 255, 255, 180))
        pen_axis.setWidth(max(1, int(2 * scale)))
        painter.setPen(pen_axis)
        x_end = center_x + inner_radius
        y_end = center_y
        painter.drawLine(center, QPointF(x_end, y_end))

        # needle pitch
        clamped_pitch = max(-90, min(90, self.pitch_deg))
        angle_rad = math.radians(clamped_pitch)
        needle_length = inner_radius
        needle_width = max(int(radius * 0.1), 3)

        tip_x = center.x() + needle_length * math.cos(angle_rad)
        tip_y = center.y() - needle_length * math.sin(angle_rad)

        base_left_x = center.x() + (needle_width / 2) * math.sin(angle_rad)
        base_left_y = center.y() + (needle_width / 2) * math.cos(angle_rad)

        base_right_x = center.x() - (needle_width / 2) * math.sin(angle_rad)
        base_right_y = center.y() - (needle_width / 2) * math.cos(angle_rad)

        needle_polygon = QPolygon([
            QPoint(int(tip_x), int(tip_y)),
            QPoint(int(base_left_x), int(base_left_y)),
            QPoint(int(base_right_x), int(base_right_y)),
        ])

        painter.setBrush(QColor(255, 165, 0))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(needle_polygon)

        # Center circle of needle
        painter.setBrush(QColor(255, 165, 0))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, max(3, int(4 * scale)), max(3, int(4 * scale)))

        # number 0°
        font = QFont("sans-serif", max(1, int(8 * scale)))
        painter.setFont(font)
        painter.setPen(QColor("white"))
        zero_label_x = center_x + inner_radius + int(15 * scale)
        zero_label_y = center_y
        zero_rect = QRectF(zero_label_x - 14, zero_label_y - 14, 28, 28)
        painter.drawText(zero_rect, Qt.AlignCenter, "0°")

        # Pitch degree compass Y
        pitch_text = f"{int(clamped_pitch)}°"
        font_pitch = QFont("sans-serif", max(1, int(8 * scale)))
        painter.setFont(font_pitch)
        painter.setPen(QColor("white"))

        text_height = int(24 * scale)
        text_rect = QRectF(
            center.x() - radius,
            center.y() + radius - text_height,
            radius * 2,
            text_height
        )
        painter.drawText(text_rect, Qt.AlignCenter, pitch_text)

# All UI Widgets Manager displayed on the screen
class UIWidgetManager:
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.widgets = {}
        self.init_widgets()
    
    # create all UI widgets 
    def init_widgets(self):
        self.create_zoom_view()
        self.create_zoom_label_text() 
        self.create_motion_fps_labels()
        self.create_play_pause_button()
        self.create_toggle_zoom_button()
    
    # create zoom view widget
    def create_zoom_view(self):
        self.widgets['zoom_view'] = QLabel(self.parent)
        self.widgets['zoom_view'].setGeometry(10, 50, 320, 240)
        self.widgets['zoom_view'].setStyleSheet("""
            background-color: black;
            border: 2px solid white;                         
        """)
        self.widgets['zoom_view'].setAlignment(Qt.AlignCenter)
        self.widgets['zoom_view'].setText("Zoom View")
        return self.widgets['zoom_view']
    
    # create zoom label text
    def create_zoom_label_text(self):
        self.widgets['zoom_label_text'] = QLabel(self.parent)
        self.widgets['zoom_label_text'].setStyleSheet("""
            color: white;
            background-color: rgba(0, 0, 0, 160);
            border-radius: 5px;
            padding: 2px 5px;
            font-size: 14px;
        """)
        self.widgets['zoom_label_text'].setAlignment(Qt.AlignCenter)
        self.widgets['zoom_label_text'].setFixedHeight(24)
        self.widgets['zoom_label_text'].show()
        return self.widgets['zoom_label_text']


    
    # create motion and FPS labels
    def create_motion_fps_labels(self):
        self.widgets['motion_label'] = QLabel(self.parent)
        self.widgets['motion_label'].setTextFormat(Qt.RichText)
        
        self.widgets['fps_label'] = QLabel(self.parent)
        
        return self.widgets['motion_label'], self.widgets['fps_label']
    
    # create play/pause button
    def create_play_pause_button(self):
        self.widgets['play_pause_button'] = QPushButton("⏸", self.parent)
        self.widgets['play_pause_button'].setGeometry(
            self.parent.width() - 120,  
            self.parent.height() - 100, 
            100, 80                         
        )

        font = self.widgets['play_pause_button'].font()
        font.setPointSize(30) 
        self.widgets['play_pause_button'].setFont(font)
        self.widgets['play_pause_button'].setStyleSheet("""
            background-color: white;
            border: 1px solid gray;
            border-radius: 8px;
            font-size: 24px;
        """)
        return self.widgets['play_pause_button']
    
    # create toggle zoom
    def create_toggle_zoom_button(self):
        icon_eye_open = qta.icon('fa5s.eye', color='white')  # กำหนดไอคอนสีขาว

        self.widgets['toggle_zoom_button'] = QPushButton(self.parent)
        self.widgets['toggle_zoom_button'].setIcon(icon_eye_open)
        self.widgets['toggle_zoom_button'].setIconSize(QSize(24, 24))
        self.widgets['toggle_zoom_button'].setFixedSize(32, 32)
        self.widgets['toggle_zoom_button'].setStyleSheet(
            "background-color: rgba(60, 60, 60, 153); border: 1px solid gray; border-radius: 6px;"
        )
        return self.widgets['toggle_zoom_button']

    
    # update widget position
    def update_widget_positions(self, video_label_width, video_label_height, nav_bar_height):
        # play/pause button
        x = 20
        y = (video_label_height - self.widgets['play_pause_button'].height()) // 2
        self.widgets['play_pause_button'].move(x, y)
        self.widgets['play_pause_button'].raise_()

        # zoom view (responsive scaling)
        zoom_width = video_label_width * 0.12
        zoom_height = zoom_width * 3 / 4
        self.widgets['zoom_view'].setGeometry(20, nav_bar_height - 30, int(zoom_width), int(zoom_height))

        # Position zoom label text under zoom view
        zoom_view = self.widgets['zoom_view']
        zoom_label = self.widgets['zoom_label_text']  # <-- แก้ตรงนี้

        zoom_label_width = zoom_view.width()
        zoom_label_height = 30
        zoom_label.setFixedSize(zoom_label_width, zoom_label_height)

        # ลบ +2 ออก เพื่อชิดขอบล่างเป๊ะ
        zoom_label.move(zoom_view.x(), zoom_view.y() + zoom_view.height())


        # toggle zoom button
        button_size = max(16, int(zoom_width * 0.12))
        self.widgets['toggle_zoom_button'].setFixedSize(button_size + 6, button_size + 6)
        self.widgets['toggle_zoom_button'].setIconSize(QSize(button_size, button_size))

        # motion and FPS labels
        base_width = video_label_width
        base_height = video_label_height
        motion_label_width = int(base_width * 0.12)
        fps_label_width = int(base_width * 0.07)

        min_font = 8
        max_font = 16
        font_size = max(min_font, min(max_font, int(base_height / 40)))

        self.widgets['motion_label'].setFixedWidth(motion_label_width)
        self.widgets['motion_label'].move(base_width - motion_label_width - fps_label_width - 30, nav_bar_height - 30)
        self.widgets['motion_label'].setStyleSheet(f"""
            font-size: {font_size}px;
            font-family: sans-serif;
            background-color: rgba(100, 100, 100, 150);
            color: white;
            border-radius: 10px;
            padding: 4px;
        """)

        self.widgets['fps_label'].setFixedWidth(fps_label_width)
        self.widgets['fps_label'].move(base_width - fps_label_width - 10, nav_bar_height - 30)
        self.widgets['fps_label'].setStyleSheet(f"""
            font-size: {font_size}px;
            font-family: sans-serif;
            background-color: rgba(100, 100, 100, 150);
            color: lime;
            border-radius: 10px;
            padding: 4px;
        """)



    # update text motion and FPS labels
    def update_motion_fps_labels(self, motion_mode, current_fps):
        self.widgets['motion_label'].setText(
            f'<span style="color: white;">Motion:</span> '
            f'<span style="color: cyan;">{motion_mode}</span>'
        )
        self.widgets['fps_label'].setText(
            f'<span style="color: white;">FPS:</span> '
            f'<span style="color: lime;">{current_fps}</span>'
        )

    
    
    #position toggle zoom
    def place_toggle_button(self, zoom_is_visible, nav_bar_height):
        self.widgets['toggle_zoom_button'].setVisible(True) 
        if zoom_is_visible:
            x = self.widgets['zoom_view'].x() + self.widgets['zoom_view'].width() + 10
            y = self.widgets['zoom_view'].y()
            self.widgets['toggle_zoom_button'].move(x, y)
        else:
            x = 10
            y = nav_bar_height - 30
            self.widgets['toggle_zoom_button'].move(x, y)
    
    # update icon play/pause
    def update_play_pause_button(self, is_paused):
        if is_paused:
            self.widgets['play_pause_button'].setText("▶️")
        else:
            self.widgets['play_pause_button'].setText("⏸")
    
    # set zoom view
    def set_zoom_view_content(self, pixmap):
        self.widgets['zoom_view'].setPixmap(pixmap)
    
    # Toggle show/hide zoom view"""
    def toggle_zoom_view_visibility(self):
        if self.widgets['zoom_view'].isVisible():
            self.widgets['zoom_view'].hide()
            return False
        else:
            self.widgets['zoom_view'].show()
            return True
    
    # Pull widget by name
    def get_widget(self, name):
        return self.widgets.get(name)
    
    # no object detection
    def draw_no_detection_message(self, frame_bgr):
        message = "No object detected"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.4
        thickness = 1

        text_size, _ = cv2.getTextSize(message, font, font_scale, thickness)
        text_width, text_height = text_size

        cx = frame_bgr.shape[1] // 2
        cy = frame_bgr.shape[0] // 2 - 220

        text_x = cx - text_width // 2
        text_y = cy + text_height // 2

        overlay = frame_bgr.copy()
        cv2.rectangle(overlay,
                    (text_x - 10, text_y - text_height - 10),
                    (text_x + text_width + 10, text_y + 10),
                    (100, 100, 100), -1)
        alpha = 0.6
        cv2.addWeighted(overlay, alpha, frame_bgr, 1 - alpha, 0, frame_bgr)

        cv2.putText(frame_bgr, message, (text_x, text_y),
                    font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
        
        return frame_bgr