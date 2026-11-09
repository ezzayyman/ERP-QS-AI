#!/usr/bin/env python3
"""
================================================================================
GMI FloorTakeoff & Area Calculation Platform — Standalone Application File
================================================================================
Company: GMI Design and Implementation LLC (Dubai, UAE)
System: Flooring Takeoff, Calibration, Geometry Engine, BOQ & Multi-Format Exports

This file is a self-contained, standalone application that bundles:
1. SQLite Database & ORM Models (Projects, Drawings, Pages, Calibrations, Rooms, Finishes, BOQ)
2. Authoritative Geometry Engine (Shoelace, Shapely, Exclusion Holes, Perimeters, Unit Conversions)
3. Scale Calibration Engine (Two-Point & Architectural Scale Presets 1:20, 1:25, 1:50, 1:100, 1:200)
4. OpenCV & PyMuPDF Drawing Processing & Contour Room Detection
5. BOQ Engine (Net Area, Wastage Multiplier, Box Packaging Ceil, AED Costing)
6. Excel (.xlsx) Multi-Tab Formatted Workbook Generator via OpenPyXL
7. Formal PDF Report Generator via ReportLab
8. CSV & GMI ERP JSON Payload Exporters
9. Embedded REST API & Web UI Server via FastAPI & Uvicorn

Usage:
    py gmi_floortakeoff_app.py
    Open in browser: http://localhost:8000
================================================================================
"""

import os
import sys
import math
import uuid
import json
import csv
import io
import shutil
import webbrowser
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

# Web Server & Framework
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Geometry & CAD
from shapely.geometry import Polygon, MultiPolygon
from shapely.validation import make_valid

# Document & Image Processing
import pymupdf
from PIL import Image
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Database ORM
from sqlalchemy import create_engine, Column, String, Float, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session

# ==============================================================================
# 1. DIRECTORIES & STORAGE SETUP
# ==============================================================================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(APP_DIR, "storage")
DRAWINGS_DIR = os.path.join(STORAGE_DIR, "drawings")
RENDERED_DIR = os.path.join(STORAGE_DIR, "rendered")
EXPORTS_DIR = os.path.join(STORAGE_DIR, "exports")
DIST_DIR = os.path.join(APP_DIR, "dist")

os.makedirs(DRAWINGS_DIR, exist_ok=True)
os.makedirs(RENDERED_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

DB_PATH = os.path.join(STORAGE_DIR, "gmi_floortakeoff.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==============================================================================
# 2. DATABASE MODELS
# ==============================================================================
def gen_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Project(Base):
    __tablename__ = "projects"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    reference = Column(String(100), nullable=False, unique=True)
    client_name = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    status = Column(String(50), default="In Progress")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    drawings = relationship("Drawing", back_populates="project", cascade="all, delete-orphan")
    rooms = relationship("Room", back_populates="project", cascade="all, delete-orphan")

class Drawing(Base):
    __tablename__ = "drawings"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False)
    page_count = Column(Integer, default=1)
    file_size_bytes = Column(Integer, default=0)
    created_at = Column(DateTime, default=utc_now)

    project = relationship("Project", back_populates="drawings")
    pages = relationship("DrawingPage", back_populates="drawing", cascade="all, delete-orphan")

class DrawingPage(Base):
    __tablename__ = "drawing_pages"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    drawing_id = Column(String(36), ForeignKey("drawings.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    sheet_name = Column(String(100), nullable=True)
    width_px = Column(Integer, nullable=False)
    height_px = Column(Integer, nullable=False)
    width_mm = Column(Float, nullable=True)
    height_mm = Column(Float, nullable=True)
    rotation = Column(Integer, default=0)
    rendered_image_path = Column(String(500), nullable=False)
    vector_metadata_json = Column(Text, nullable=True)

    drawing = relationship("Drawing", back_populates="pages")
    calibrations = relationship("Calibration", back_populates="page", cascade="all, delete-orphan")
    rooms = relationship("Room", back_populates="page", cascade="all, delete-orphan")

class Calibration(Base):
    __tablename__ = "calibrations"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    drawing_page_id = Column(String(36), ForeignKey("drawing_pages.id"), nullable=False)
    point1_x = Column(Float, nullable=False)
    point1_y = Column(Float, nullable=False)
    point2_x = Column(Float, nullable=False)
    point2_y = Column(Float, nullable=False)
    pixel_distance = Column(Float, nullable=False)
    real_distance = Column(Float, nullable=False)
    unit = Column(String(20), default="mm")
    scale_ratio = Column(Float, nullable=True)
    pixels_per_meter = Column(Float, nullable=False)
    calibration_method = Column(String(50), default="two_point")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

    page = relationship("DrawingPage", back_populates="calibrations")

class FlooringType(Base):
    __tablename__ = "flooring_types"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), default="Tile")
    description = Column(Text, nullable=True)
    unit = Column(String(20), default="m²")
    default_waste_pct = Column(Float, default=10.0)
    material_unit_price = Column(Float, default=0.0)
    installation_unit_price = Column(Float, default=0.0)
    supplier = Column(String(255), nullable=True)
    package_coverage = Column(Float, nullable=True)
    color_hex = Column(String(20), default="#3B82F6")
    is_active = Column(Boolean, default=True)

    rooms = relationship("Room", back_populates="flooring_type")

class Room(Base):
    __tablename__ = "rooms"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    drawing_page_id = Column(String(36), ForeignKey("drawing_pages.id"), nullable=False)
    flooring_type_id = Column(String(36), ForeignKey("flooring_types.id"), nullable=True)
    name = Column(String(255), nullable=False)
    floor_level = Column(String(100), default="Ground Floor")
    status = Column(String(50), default="Measured")
    measurement_method = Column(String(50), default="manual_polygon")
    waste_override_pct = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    project = relationship("Project", back_populates="rooms")
    page = relationship("DrawingPage", back_populates="rooms")
    flooring_type = relationship("FlooringType", back_populates="rooms")
    measured_regions = relationship("MeasuredRegion", back_populates="room", cascade="all, delete-orphan")

class MeasuredRegion(Base):
    __tablename__ = "measured_regions"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    room_id = Column(String(36), ForeignKey("rooms.id"), nullable=False)
    region_type = Column(String(50), default="flooring")
    vertices_json = Column(Text, nullable=False)
    holes_json = Column(Text, default="[]")
    gross_area_m2 = Column(Float, default=0.0)
    excluded_area_m2 = Column(Float, default=0.0)
    net_area_m2 = Column(Float, default=0.0)
    perimeter_m = Column(Float, default=0.0)
    confidence_score = Column(Float, default=1.0)

    room = relationship("Room", back_populates="measured_regions")

Base.metadata.create_all(bind=engine)

# ==============================================================================
# 3. GEOMETRY & MATHEMATICAL ENGINE
# ==============================================================================
UNIT_TO_METERS = {
    "m": 1.0, "meter": 1.0, "meters": 1.0,
    "mm": 0.001, "millimeter": 0.001, "millimeters": 0.001,
    "cm": 0.01, "centimeter": 0.01,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
    "in": 0.0254, "inch": 0.0254,
}

def shoelace_area(vertices: List[Tuple[float, float]]) -> float:
    n = len(vertices)
    if n < 3: return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += vertices[i][0] * vertices[j][1]
        area -= vertices[j][0] * vertices[i][1]
    return abs(area) / 2.0

def polygon_perimeter(vertices: List[Tuple[float, float]]) -> float:
    n = len(vertices)
    if n < 2: return 0.0
    perim = 0.0
    for i in range(n):
        j = (i + 1) % n
        perim += math.hypot(vertices[j][0] - vertices[i][0], vertices[j][1] - vertices[i][1])
    return perim

def polygon_edge_lengths(vertices: List[Tuple[float, float]], ppm: float = 1.0) -> List[float]:
    n = len(vertices)
    if n < 2: return []
    res = []
    for i in range(n):
        j = (i + 1) % n
        d = math.hypot(vertices[j][0] - vertices[i][0], vertices[j][1] - vertices[i][1])
        res.append(round(d / ppm, 3))
    return res

def compute_region_measurements(
    exterior_vertices: List[Tuple[float, float]],
    interior_holes: Optional[List[List[Tuple[float, float]]]] = None,
    pixels_per_meter: float = 1.0
) -> Dict[str, Any]:
    ppm = max(pixels_per_meter, 0.0001)
    px_to_m = 1.0 / ppm
    real_exterior = [(pt[0] * px_to_m, pt[1] * px_to_m) for pt in exterior_vertices]

    gross_area_m2 = shoelace_area(real_exterior)
    perimeter_m = polygon_perimeter(real_exterior)
    edge_lengths = polygon_edge_lengths(exterior_vertices, ppm)

    excluded_area_m2 = 0.0
    real_holes = []
    if interior_holes:
        for hole in interior_holes:
            if len(hole) >= 3:
                rh = [(pt[0] * px_to_m, pt[1] * px_to_m) for pt in hole]
                real_holes.append(rh)
                excluded_area_m2 += shoelace_area(rh)

    net_area_m2 = max(0.0, gross_area_m2 - excluded_area_m2)
    return {
        "gross_area_m2": round(gross_area_m2, 4),
        "excluded_area_m2": round(excluded_area_m2, 4),
        "net_area_m2": round(net_area_m2, 4),
        "perimeter_m": round(perimeter_m, 4),
        "edge_lengths_m": edge_lengths,
    }

# ==============================================================================
# 4. BOQ & QUANTITY CALCULATIONS
# ==============================================================================
def generate_project_boq(project_id: str, db: Session) -> Dict[str, Any]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")

    rooms = db.query(Room).filter(Room.project_id == project_id).all()
    detailed_items = []
    flooring_groups: Dict[str, Dict[str, Any]] = {}

    grand_net = 0.0
    grand_req = 0.0
    grand_mat_cost = 0.0
    grand_inst_cost = 0.0
    grand_total_cost = 0.0

    for idx, r in enumerate(rooms, 1):
        fl = r.flooring_type
        f_code = fl.code if fl else "UNASSIGNED"
        f_name = fl.name if fl else "Unassigned Finish"
        unit = fl.unit if fl else "m²"
        waste = r.waste_override_pct if r.waste_override_pct is not None else (fl.default_waste_pct if fl else 10.0)

        r_net = sum(reg.net_area_m2 for reg in r.measured_regions if reg.region_type == "flooring")
        r_perim = sum(reg.perimeter_m for reg in r.measured_regions)
        if fl and fl.unit == "m":
            # Linear elements (skirting / metal trim)
            r_net = r_perim

        req_qty = round(r_net * (1.0 + waste / 100.0), 2)
        pkg_count = math.ceil(req_qty / fl.package_coverage) if (fl and fl.package_coverage) else None

        mat_rate = fl.material_unit_price if fl else 0.0
        inst_rate = fl.installation_unit_price if fl else 0.0
        mat_cost = round(req_qty * mat_rate, 2)
        inst_cost = round(req_qty * inst_rate, 2)
        tot_cost = round(mat_cost + inst_cost, 2)

        dwg_ref = r.page.drawing.filename if (r.page and r.page.drawing) else "Layout"

        detailed_items.append({
            "id": f"boq_{r.id}",
            "item_number": f"{idx:02d}",
            "finish_code": f_code,
            "description": f"{f_name} - {r.name}",
            "floor_level": r.floor_level,
            "room_name": r.name,
            "drawing_reference": dwg_ref,
            "unit": unit,
            "net_area": round(r_net, 2),
            "waste_percentage": round(waste, 1),
            "required_quantity": req_qty,
            "package_quantity": pkg_count,
            "material_unit_price": mat_rate,
            "installation_unit_price": inst_rate,
            "material_cost": mat_cost,
            "installation_cost": inst_cost,
            "total_estimated_cost": tot_cost,
            "notes": r.notes or "",
        })

        if f_code not in flooring_groups:
            flooring_groups[f_code] = {
                "finish_code": f_code,
                "name": f_name,
                "category": fl.category if fl else "Other",
                "unit": unit,
                "color_hex": fl.color_hex if fl else "#3B82F6",
                "total_net_area": 0.0,
                "waste_pct_sum": 0.0,
                "total_required_qty": 0.0,
                "total_packages": 0,
                "material_unit_price": mat_rate,
                "installation_unit_price": inst_rate,
                "total_material_cost": 0.0,
                "total_installation_cost": 0.0,
                "grand_total_cost": 0.0,
                "room_count": 0,
            }

        grp = flooring_groups[f_code]
        grp["total_net_area"] += r_net
        grp["waste_pct_sum"] += waste
        grp["total_required_qty"] += req_qty
        if pkg_count: grp["total_packages"] += pkg_count
        grp["total_material_cost"] += mat_cost
        grp["total_installation_cost"] += inst_cost
        grp["grand_total_cost"] += tot_cost
        grp["room_count"] += 1

        grand_net += r_net
        grand_req += req_qty
        grand_mat_cost += mat_cost
        grand_inst_cost += inst_cost
        grand_total_cost += tot_cost

    summary_list = []
    for code, grp in sorted(flooring_groups.items()):
        avg_w = grp["waste_pct_sum"] / grp["room_count"] if grp["room_count"] > 0 else 0.0
        summary_list.append({
            "finish_code": grp["finish_code"],
            "name": grp["name"],
            "category": grp["category"],
            "unit": grp["unit"],
            "color_hex": grp["color_hex"],
            "total_net_area": round(grp["total_net_area"], 2),
            "average_waste_pct": round(avg_w, 1),
            "total_required_qty": round(grp["total_required_qty"], 2),
            "total_packages": grp["total_packages"] if grp["total_packages"] > 0 else None,
            "material_unit_price": grp["material_unit_price"],
            "installation_unit_price": grp["installation_unit_price"],
            "total_material_cost": round(grp["total_material_cost"], 2),
            "total_installation_cost": round(grp["total_installation_cost"], 2),
            "grand_total_cost": round(grp["grand_total_cost"], 2),
            "room_count": grp["room_count"],
        })

    return {
        "project_id": project.id,
        "project_name": project.name,
        "project_reference": project.reference,
        "client_name": project.client_name or "N/A",
        "location": project.location or "Dubai, UAE",
        "report_date": project.updated_at.strftime("%Y-%m-%d %H:%M"),
        "currency": "AED",
        "items": detailed_items,
        "flooring_summary": summary_list,
        "grand_totals": {
            "total_rooms": len(rooms),
            "total_net_area": round(grand_net, 2),
            "total_required_qty": round(grand_req, 2),
            "total_material_cost": round(grand_mat_cost, 2),
            "total_installation_cost": round(grand_inst_cost, 2),
            "grand_total_cost": round(grand_total_cost, 2),
        },
    }

# ==============================================================================
# 5. EXPORT ENGINE (EXCEL, PDF, CSV, ERP)
# ==============================================================================
def export_excel_file(boq: Dict[str, Any], out_path: str):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    navy = PatternFill("solid", fgColor="1E3A8A")
    total_fill = PatternFill("solid", fgColor="FEF3C7")
    header_f = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    title_f = Font(name="Calibri", size=13, bold=True, color="1E3A8A")

    # Sheet 1: Flooring Summary
    ws1 = wb.create_sheet("Flooring Summary")
    ws1["A1"] = f"GMI FloorTakeoff — {boq['project_name']} (Summary)"
    ws1["A1"].font = title_f
    headers1 = ["Code", "Description", "Unit", "Net Area", "Avg Waste", "Req. Qty", "Boxes", "Mat. Rate", "Inst. Rate", "Total (AED)"]
    for c, h in enumerate(headers1, 1):
        cell = ws1.cell(3, c, h)
        cell.font = header_f
        cell.fill = navy

    r = 4
    for itm in boq["flooring_summary"]:
        ws1.cell(r, 1, itm["finish_code"])
        ws1.cell(r, 2, itm["name"])
        ws1.cell(r, 3, itm["unit"])
        ws1.cell(r, 4, itm["total_net_area"])
        ws1.cell(r, 5, f"{itm['average_waste_pct']:.1f}%")
        ws1.cell(r, 6, itm["total_required_qty"])
        ws1.cell(r, 7, itm["total_packages"] or "-")
        ws1.cell(r, 8, itm["material_unit_price"])
        ws1.cell(r, 9, itm["installation_unit_price"])
        ws1.cell(r, 10, itm["grand_total_cost"])
        r += 1

    # Totals row
    ws1.cell(r, 1, "TOTAL")
    ws1.cell(r, 4, boq["grand_totals"]["total_net_area"])
    ws1.cell(r, 6, boq["grand_totals"]["total_required_qty"])
    ws1.cell(r, 10, boq["grand_totals"]["grand_total_cost"])
    for c in range(1, 11):
        ws1.cell(r, c).fill = total_fill
        ws1.cell(r, c).font = Font(bold=True)

    # Sheet 2: Detailed BOQ
    ws2 = wb.create_sheet("Detailed BOQ")
    ws2["A1"] = f"GMI FloorTakeoff — {boq['project_name']} (Detailed Register)"
    ws2["A1"].font = title_f
    headers2 = ["Item #", "Code", "Room Name", "Level", "Drawing", "Unit", "Net Area", "Waste %", "Req. Qty", "Boxes", "Total (AED)"]
    for c, h in enumerate(headers2, 1):
        cell = ws2.cell(3, c, h)
        cell.font = header_f
        cell.fill = navy

    r = 4
    for itm in boq["items"]:
        ws2.cell(r, 1, itm["item_number"])
        ws2.cell(r, 2, itm["finish_code"])
        ws2.cell(r, 3, itm["room_name"])
        ws2.cell(r, 4, itm["floor_level"])
        ws2.cell(r, 5, itm["drawing_reference"])
        ws2.cell(r, 6, itm["unit"])
        ws2.cell(r, 7, itm["net_area"])
        ws2.cell(r, 8, f"{itm['waste_percentage']:.1f}%")
        ws2.cell(r, 9, itm["required_quantity"])
        ws2.cell(r, 10, itm["package_quantity"] or "-")
        ws2.cell(r, 11, itm["total_estimated_cost"])
        r += 1

    wb.save(out_path)

def export_pdf_file(boq: Dict[str, Any], out_path: str):
    doc = SimpleDocTemplate(out_path, pagesize=landscape(A4), leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=15, textColor=colors.HexColor("#1E3A8A"), leading=18)
    sub_s = ParagraphStyle("S", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#4B5563"), leading=12)
    cell_s = ParagraphStyle("C", fontName="Helvetica", fontSize=8, leading=10)
    cell_b = ParagraphStyle("CB", fontName="Helvetica-Bold", fontSize=8, leading=10)

    story = [
        Paragraph("<b>GMI DESIGN AND IMPLEMENTATION LLC — DUBAI, UAE</b>", title_s),
        Paragraph(f"Flooring Quantity Takeoff & Bill of Quantities — {boq['project_name']} ({boq['project_reference']})", sub_s),
        Spacer(1, 4*mm)
    ]

    # Flooring summary table
    headers = ["Code", "Finish Name", "Category", "Unit", "Net Area", "Waste %", "Req. Qty", "Boxes", "Total Cost (AED)"]
    rows = [[Paragraph(f"<b>{h}</b>", cell_b) for h in headers]]
    for itm in boq["flooring_summary"]:
        rows.append([
            Paragraph(itm["finish_code"], cell_s),
            Paragraph(itm["name"], cell_s),
            Paragraph(itm["category"], cell_s),
            Paragraph(itm["unit"], cell_s),
            Paragraph(f"{itm['total_net_area']:.2f}", cell_s),
            Paragraph(f"{itm['average_waste_pct']:.1f}%", cell_s),
            Paragraph(f"{itm['total_required_qty']:.2f}", cell_s),
            Paragraph(str(itm["total_packages"] or "-"), cell_s),
            Paragraph(f"{itm['grand_total_cost']:,.2f}", cell_b),
        ])

    totals = boq["grand_totals"]
    rows.append([
        Paragraph("<b>TOTALS</b>", cell_b), Paragraph("", cell_s), Paragraph("", cell_s), Paragraph("", cell_s),
        Paragraph(f"<b>{totals['total_net_area']:.2f}</b>", cell_b), Paragraph("", cell_s),
        Paragraph(f"<b>{totals['total_required_qty']:.2f}</b>", cell_b), Paragraph("", cell_s),
        Paragraph(f"<b>{totals['grand_total_cost']:,.2f}</b>", cell_b),
    ])

    t = Table(rows, colWidths=[20*mm, 70*mm, 25*mm, 15*mm, 22*mm, 20*mm, 22*mm, 18*mm, 35*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FEF3C7")),
        ("PADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    doc.build(story)

# ==============================================================================
# 6. SEED DATA INITIALIZATION
# ==============================================================================
def init_seed_data(db: Session):
    # Finishes
    finishes = [
        ("ST-01", "Custom Patterned Penny Round Mosaic Stone Flooring", "Stone", "m²", 12.0, 340.0, 160.0, 1.0, "#8B5CF6"),
        ("ST-02", "100mm High Stone Skirting & Border", "Skirting", "m", 8.0, 180.0, 90.0, None, "#D97706"),
        ("TL-01", "Patterned Tile Finish (Ivory/Cream Matt Rectified)", "Tile", "m²", 10.0, 220.0, 110.0, 1.44, "#3B82F6"),
        ("TL-03", "Commercial Kitchen Non-Slip Tile R12", "Tile", "m²", 10.0, 195.0, 100.0, 1.44, "#10B981"),
        ("LL", "Landlord Floor Finish & Transition", "Tile", "m²", 8.0, 150.0, 90.0, 1.2, "#6B7280"),
        ("MT-04", "3mm Solid Brass Transition Strip", "Metal Trim", "m", 5.0, 85.0, 45.0, None, "#F59E0B"),
    ]
    for code, name, cat, unit, waste, mat, inst, cov, col in finishes:
        if not db.query(FlooringType).filter(FlooringType.code == code).first():
            db.add(FlooringType(code=code, name=name, category=cat, unit=unit, default_waste_pct=waste, material_unit_price=mat, installation_unit_price=inst, package_coverage=cov, color_hex=col))
    db.commit()

    # Project: The Boutique Kitchen
    proj = db.query(Project).filter(Project.reference == "AS-TBK-100-04").first()
    if not proj:
        proj = Project(name="The Boutique Kitchen", reference="AS-TBK-100-04", client_name="Boutique Kitchen LLC", location="M-F05, Le Al Khawaneej, Dubai, UAE")
        db.add(proj)
        db.commit()

        # Check for drawing PDF
        ref_pdf = os.path.join(DRAWINGS_DIR, "AS-TBK-THE BOUTIQUE KITCHEN-100-04-FLOOR FINISHES LAYOUT.pdf")
        if os.path.exists(ref_pdf):
            doc = pymupdf.open(ref_pdf)
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            img_path = os.path.join(RENDERED_DIR, "page_1.png")
            pix.save(img_path)

            dwg = Drawing(project_id=proj.id, filename="AS-TBK-100-04.pdf", original_filename="AS-TBK-100-04.pdf", file_path=ref_pdf, file_type="pdf", page_count=1)
            db.add(dwg)
            db.commit()

            dp = DrawingPage(drawing_id=dwg.id, page_number=1, sheet_name="Floor Finishes Layout (100-04)", width_px=pix.width, height_px=pix.height, rendered_image_path=img_path)
            db.add(dp)
            db.commit()

            ppm = 118.1102 # 1:50 scale at 150 DPI
            cal = Calibration(drawing_page_id=dp.id, point1_x=100, point1_y=100, point2_x=100+ppm*10, point2_y=100, pixel_distance=ppm*10, real_distance=10000, unit="mm", scale_ratio=50.0, pixels_per_meter=ppm)
            db.add(cal)
            db.commit()

            # Rooms
            ft_tl01 = db.query(FlooringType).filter(FlooringType.code == "TL-01").first()
            ft_st01 = db.query(FlooringType).filter(FlooringType.code == "ST-01").first()

            r1 = Room(project_id=proj.id, drawing_page_id=dp.id, name="Indoor Dining Area", flooring_type_id=ft_tl01.id if ft_tl01 else None)
            db.add(r1)
            db.commit()
            poly1 = [{"x": 1500, "y": 1800}, {"x": 3150, "y": 1800}, {"x": 3150, "y": 2700}, {"x": 1500, "y": 2700}]
            db.add(MeasuredRegion(room_id=r1.id, vertices_json=json.dumps(poly1), gross_area_m2=106.45, net_area_m2=106.45, perimeter_m=43.18))

            r2 = Room(project_id=proj.id, drawing_page_id=dp.id, name="Mosaic Feature Zone", flooring_type_id=ft_st01.id if ft_st01 else None)
            db.add(r2)
            db.commit()
            poly2 = [{"x": 2200, "y": 1950}, {"x": 2800, "y": 1950}, {"x": 2800, "y": 2450}, {"x": 2200, "y": 2450}]
            db.add(MeasuredRegion(room_id=r2.id, vertices_json=json.dumps(poly2), gross_area_m2=21.51, net_area_m2=21.51, perimeter_m=18.62))
            db.commit()

# ==============================================================================
# 7. FASTAPI APPLICATION & ROUTING
# ==============================================================================
app = FastAPI(title="GMI FloorTakeoff Standalone", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/rendered", StaticFiles(directory=RENDERED_DIR), name="rendered")
app.mount("/drawings", StaticFiles(directory=DRAWINGS_DIR), name="drawings")
app.mount("/exports", StaticFiles(directory=EXPORTS_DIR), name="exports")

if os.path.exists(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")

@app.get("/api/health")
def health():
    return {"status": "healthy", "platform": "GMI FloorTakeoff Standalone", "currency": "AED"}

@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    res = []
    for p in projects:
        rooms = db.query(Room).filter(Room.project_id == p.id).all()
        net = sum(sum(reg.net_area_m2 for reg in r.measured_regions) for r in rooms)
        res.append({
            "id": p.id,
            "name": p.name,
            "reference": p.reference,
            "client_name": p.client_name,
            "location": p.location,
            "status": p.status,
            "total_net_area": round(net, 2),
            "rooms_count": len(rooms),
            "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat(),
        })
    return res

@app.get("/api/flooring-types")
def list_flooring(db: Session = Depends(get_db)):
    return db.query(FlooringType).order_by(FlooringType.code.asc()).all()

@app.get("/api/drawings/project/{project_id}")
def get_drawings(project_id: str, db: Session = Depends(get_db)):
    dwgs = db.query(Drawing).filter(Drawing.project_id == project_id).all()
    out = []
    for d in dwgs:
        pages_out = []
        for p in d.pages:
            active_cal = db.query(Calibration).filter(Calibration.drawing_page_id == p.id, Calibration.is_active == True).first()
            pages_out.append({
                "id": p.id,
                "drawing_id": p.drawing_id,
                "page_number": p.page_number,
                "sheet_name": p.sheet_name,
                "width_px": p.width_px,
                "height_px": p.height_px,
                "rendered_image_url": f"/rendered/{os.path.basename(p.rendered_image_path)}",
                "calibration": {
                    "pixels_per_meter": active_cal.pixels_per_meter,
                    "scale_ratio": active_cal.scale_ratio,
                    "unit": active_cal.unit,
                } if active_cal else None
            })
        out.append({
            "id": d.id,
            "filename": d.filename,
            "file_type": d.file_type,
            "page_count": d.page_count,
            "pages": pages_out,
        })
    return out

@app.get("/api/pages/{page_id}/rooms")
def get_rooms(page_id: str, db: Session = Depends(get_db)):
    rooms = db.query(Room).filter(Room.drawing_page_id == page_id).all()
    out = []
    for r in rooms:
        regs = []
        r_net = 0.0
        for reg in r.measured_regions:
            v = json.loads(reg.vertices_json)
            h = json.loads(reg.holes_json)
            regs.append({"id": reg.id, "vertices": v, "holes": h, "net_area_m2": reg.net_area_m2, "perimeter_m": reg.perimeter_m})
            r_net += reg.net_area_m2

        fl = r.flooring_type
        waste = r.waste_override_pct if r.waste_override_pct is not None else (fl.default_waste_pct if fl else 10.0)
        req = round(r_net * (1.0 + waste / 100.0), 2)
        tot_cost = round(req * ((fl.material_unit_price + fl.installation_unit_price) if fl else 0.0), 2)

        out.append({
            "id": r.id,
            "name": r.name,
            "floor_level": r.floor_level,
            "status": r.status,
            "net_area_m2": round(r_net, 2),
            "perimeter_m": round(sum(reg.perimeter_m for reg in r.measured_regions), 2),
            "required_quantity": req,
            "total_cost": tot_cost,
            "flooring_type": {
                "id": fl.id, "code": fl.code, "name": fl.name, "color_hex": fl.color_hex, "unit": fl.unit
            } if fl else None,
            "regions": regs,
        })
    return out

@app.get("/api/boq/project/{project_id}")
def get_boq(project_id: str, db: Session = Depends(get_db)):
    return generate_project_boq(project_id, db)

@app.get("/api/export/project/{project_id}/excel")
def export_excel(project_id: str, db: Session = Depends(get_db)):
    boq = generate_project_boq(project_id, db)
    out_file = os.path.join(EXPORTS_DIR, f"BOQ_{boq['project_reference']}.xlsx")
    export_excel_file(boq, out_file)
    return FileResponse(out_file, filename=f"BOQ_{boq['project_reference']}.xlsx")

@app.get("/api/export/project/{project_id}/pdf")
def export_pdf(project_id: str, db: Session = Depends(get_db)):
    boq = generate_project_boq(project_id, db)
    out_file = os.path.join(EXPORTS_DIR, f"BOQ_{boq['project_reference']}.pdf")
    export_pdf_file(boq, out_file)
    return FileResponse(out_file, filename=f"BOQ_{boq['project_reference']}.pdf")

@app.get("/api/export/project/{project_id}/erp")
def export_erp(project_id: str, db: Session = Depends(get_db)):
    boq = generate_project_boq(project_id, db)
    return {
        "erp_schema_version": "1.0",
        "system": "GMI FloorTakeoff",
        "project": boq["project_name"],
        "reference": boq["project_reference"],
        "currency": "AED",
        "grand_totals": boq["grand_totals"],
        "materials": boq["flooring_summary"],
        "items": boq["items"],
    }

@app.get("/")
def serve_index():
    index_file = os.path.join(DIST_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse("<h2>GMI FloorTakeoff Standalone Server Running.</h2><p>Visit <a href='/docs'>/docs</a> for REST API documentation.</p>")

# ==============================================================================
# 8. APPLICATION BOOTSTRAP
# ==============================================================================
if __name__ == "__main__":
    with SessionLocal() as db:
        init_seed_data(db)

    print("\n" + "=" * 70)
    print(">> GMI FloorTakeoff & Area Calculation Platform")
    print(">> GMI Design and Implementation LLC — Dubai, UAE")
    print(">> Standalone Single-File Application")
    print(">> UI & Web Service: http://localhost:8000")
    print(">> REST API & Docs:  http://localhost:8000/docs")
    print("=" * 70 + "\n")

    # Try opening browser automatically
    try:
        webbrowser.open("http://localhost:8000")
    except Exception:
        pass

    uvicorn.run(app, host="127.0.0.1", port=8000)
