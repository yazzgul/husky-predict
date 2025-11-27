import jsPDF from "jspdf";
import { robotoFontBase64 } from "../assets/fonts/robotoFontBase64";

export const createPDFWithCyrillicSupport = () => {
    const pdf = new jsPDF("p", "mm", "a4");
    pdf.setLanguage("ru");
    pdf.addFileToVFS("Roboto-Regular.ttf", robotoFontBase64);
    pdf.addFont("Roboto-Regular.ttf", "Roboto", "normal");
    pdf.setFont("Roboto");
    pdf.setProperties({
        title: "Карточка собаки",
        subject: "Родословная",
        author: "Husky Pedigree System",
        creator: "Husky Pedigree System",
    });
    return pdf;
};