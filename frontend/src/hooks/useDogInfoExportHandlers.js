import { useState } from "react";
import jsPDF from "jspdf";
import domtoimage from "dom-to-image";
import { robotoFontBase64 } from "../assets/fonts/robotoFontBase64";
import { convertHuskyUrl, formatDate } from "../utils/fieldConverters";
import { createPDFWithCyrillicSupport, getStatusTags } from "../utils";

export const useDogInfoExportHandlers = (dog, pedigreeTreeRef) => {
    const [modalLoading, setModalLoading] = useState(false);
    const [pdfLoading, setPdfLoading] = useState(false);

    // Handler for exporting pedigree tree to PNG
    const handleExportToPNG = async () => {
        try {
            if (!pedigreeTreeRef.current) {
                alert("Область родословной не найдена");
                return;
            }

            setModalLoading(true);

            // Экспортируем весь HTML-контейнер с помощью dom-to-image
            const dataUrl = await domtoimage.toPng(pedigreeTreeRef.current, {
                quality: 1.0,
                bgcolor: "#ffffff",
                width: pedigreeTreeRef.current.scrollWidth - 100,
                height: pedigreeTreeRef.current.scrollHeight,
                style: {
                    transform: "scale(1.2)",
                    transformOrigin: "top left",
                },
            });

            // Convert data URL to blob and download
            const response = await fetch(dataUrl);
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `pedigree_${dog.registered_name.replace(
                /[^a-zA-Z0-9]/g,
                "_"
            )}.png`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error("Ошибка при экспорте в PNG:", error);
            alert("Ошибка при создании скриншота");
        } finally {
            setModalLoading(false);
        }
    };

    // Handler for exporting entire page to PDF
    const handleExportToPDF = async () => {
        try {
            if (!pedigreeTreeRef.current) {
                alert("Страница не найдена");
                return;
            }

            // Show loading state
            setPdfLoading(true);

            // Create PDF document with UTF-8 support
            const pdf = createPDFWithCyrillicSupport();

            const pageWidth = pdf.internal.pageSize.getWidth();
            const pageHeight = pdf.internal.pageSize.getHeight();
            const margin = 10;
            let currentY = 20;

            // Add title page
            pdf.setFontSize(20);
            pdf.text("Карточка собаки", pageWidth / 2, currentY, { align: "center" });
            currentY += 15;

            // Add dog image if available
            const photoUrls = dog?.photo_url
                ? dog?.photo_url
                    .split(";")
                    .map((url) => url.trim())
                    .filter(Boolean)
                : [];

            if (photoUrls.length > 0) {
                try {
                    console.log(photoUrls);
                    // Get the first photo
                    const imageUrl = convertHuskyUrl(photoUrls[0]);
                    console.log(imageUrl);

                    // Try to load image using fetch to handle CORS
                    let imageData;
                    try {
                        // Try to fetch the image as blob
                        const response = await fetch(imageUrl, {
                            mode: "no-cors", // This might work for some servers
                            cache: "no-cache",
                        });

                        if (response.type === "opaque") {
                            // If we get an opaque response, we can't use it
                            throw new Error("Opaque response due to CORS");
                        }

                        const blob = await response.blob();
                        const reader = new FileReader();
                        imageData = await new Promise((resolve, reject) => {
                            reader.onload = () => resolve(reader.result);
                            reader.onerror = reject;
                            reader.readAsDataURL(blob);
                        });
                    } catch (fetchError) {
                        console.warn("Fetch approach failed:", fetchError);

                        // Try the original image loading approach as fallback
                        const img = new Image();
                        img.crossOrigin = "anonymous";

                        imageData = await new Promise((resolve, reject) => {
                            img.onload = () => {
                                // Create canvas to convert image to base64
                                const canvas = document.createElement("canvas");
                                const ctx = canvas.getContext("2d");
                                canvas.width = img.width;
                                canvas.height = img.height;

                                try {
                                    ctx.drawImage(img, 0, 0);
                                    const dataUrl = canvas.toDataURL("image/jpeg", 0.8);
                                    resolve(dataUrl);
                                } catch (drawError) {
                                    console.warn(
                                        "Failed to draw image to canvas (CORS issue):",
                                        drawError
                                    );
                                    reject(
                                        new Error("Cannot process image due to CORS restrictions")
                                    );
                                }
                            };
                            img.onerror = () => {
                                console.warn("Failed to load image:", imageUrl);
                                reject(new Error("Failed to load image"));
                            };
                            img.src = imageUrl;
                        });
                    }

                    // Calculate image dimensions for PDF
                    const maxImageWidth = pageWidth - 2 * margin;
                    const maxImageHeight = 60; // Maximum height for the image
                    const imageAspectRatio = img.width / img.height;

                    let imageWidth = maxImageWidth;
                    let imageHeight = imageWidth / imageAspectRatio;

                    if (imageHeight > maxImageHeight) {
                        imageHeight = maxImageHeight;
                        imageWidth = imageHeight * imageAspectRatio;
                    }

                    // Add image to PDF
                    pdf.addImage(
                        imageData,
                        "JPEG",
                        margin,
                        currentY,
                        imageWidth,
                        imageHeight
                    );
                    currentY += imageHeight + 10; // Add some space after image
                } catch (error) {
                    console.warn("All image loading approaches failed:", error);
                    // Skip adding image to PDF if all approaches fail
                    console.log("Continuing PDF creation without image");
                }
            }

            pdf.setFontSize(14);
            pdf.text(`Регистрационное имя: ${dog.registered_name}`, margin, currentY);
            currentY += 8;

            if (dog.call_name) {
                pdf.text(`Домашняя кличка: "${dog.call_name}"`, margin, currentY);
                currentY += 8;
            }

            pdf.text(
                `Дата выгрузки отчета: ${new Date().toLocaleDateString("ru-RU")}`,
                margin,
                currentY
            );
            currentY += 15;

            // Add status tags
            const statusTags = getStatusTags(dog);
            if (statusTags.length > 0) {
                pdf.setFontSize(12);
                pdf.text("Статус:", margin, currentY);
                currentY += 6;

                pdf.setFontSize(10);
                statusTags.forEach((tag) => {
                    pdf.text(`• ${tag.label}`, margin + 5, currentY);
                    currentY += 5;
                });
                currentY += 5;
            }

            // Add basic information
            pdf.setFontSize(12);
            pdf.text("Основная информация:", margin, currentY);
            currentY += 8;

            pdf.setFontSize(10);

            // Left column
            const leftColumnX = margin;
            const rightColumnX = pageWidth / 2 + 5;
            let leftY = currentY;
            let rightY = currentY;

            // Sex
            pdf.text(
                `Пол: ${dog.sex === 1 ? "Мужской" : "Женский"}`,
                leftColumnX,
                leftY
            );
            leftY += 6;

            // Color
            const colorText = dog.color
                ? dog.color_marking
                    ? `${dog.color} (${dog.color_marking})`
                    : dog.color
                : "—";
            pdf.text(`Окрас: ${colorText}`, leftColumnX, leftY);
            leftY += 6;

            // Eyes color
            pdf.text(`Цвет глаз: ${dog.eyes_color || "—"}`, leftColumnX, leftY);
            leftY += 6;

            // Size
            pdf.text(`Размер: ${dog.size || "—"}`, leftColumnX, leftY);
            leftY += 6;

            // Weight
            pdf.text(`Вес: ${dog.weight || "—"}`, leftColumnX, leftY);
            leftY += 6;

            // Right column
            // Birth date
            pdf.text(
                `Дата рождения: ${formatDate(dog.date_of_birth)}`,
                rightColumnX,
                rightY
            );
            rightY += 6;

            // Death date
            if (dog.date_of_death) {
                pdf.text(
                    `Дата смерти: ${formatDate(dog.date_of_death)}`,
                    rightColumnX,
                    rightY
                );
                rightY += 6;
            }

            // Birth country
            pdf.text(
                `Страна рождения: ${dog.land_of_birth || "—"}`,
                rightColumnX,
                rightY
            );
            rightY += 6;

            // Standing country
            pdf.text(
                `Страна проживания: ${dog.land_of_standing || "—"}`,
                rightColumnX,
                rightY
            );
            rightY += 6;

            // Registration number
            pdf.text(
                `Регистрационный номер: ${dog.registration_number || "—"}`,
                rightColumnX,
                rightY
            );
            rightY += 6;

            // Source
            pdf.text(`Источник: ${dog.source || "—"}`, rightColumnX, rightY);
            rightY += 6;

            currentY = Math.max(leftY, rightY) + 10;

            // Add COI information
            if (dog.coi !== null) {
                pdf.setFontSize(12);
                pdf.text("Информация о COI:", margin, currentY);
                currentY += 8;

                pdf.setFontSize(10);
                pdf.text(
                    `COI: ${dog.coi}% (Обновлено: ${formatDate(
                        dog.coi_updated_on,
                        true
                    )})`,
                    margin,
                    currentY
                );
                currentY += 10;
            }

            // Check if we need a new page for additional data
            if (currentY > pageHeight) {
                pdf.addPage();
                currentY = 20;
            }

            // Add titles section
            if (dog.titles && dog.titles.length > 0) {
                pdf.setFontSize(12);
                pdf.text("Титулы:", margin, currentY);
                currentY += 8;

                pdf.setFontSize(10);
                dog.titles.forEach((title) => {
                    const titleText = `${title.long_name} — ${title.short_name}`;
                    const yearText =
                        title.has_winner_year && title.winner_year
                            ? ` (${title.winner_year})`
                            : "";
                    const typeText = title.is_prefix ? " [Prefix]" : " [Suffix]";
                    const fullText = titleText + yearText + typeText;

                    // Check if text fits on current line
                    if (currentY > pageHeight - 20) {
                        pdf.addPage();
                        currentY = 20;
                    }

                    pdf.text(fullText, margin + 5, currentY);
                    currentY += 5;
                });
                currentY += 5;
            }

            // Add prefix/suffix titles
            if (dog.prefix_titles || dog.suffix_titles) {
                pdf.setFontSize(10);

                if (dog.prefix_titles) {
                    pdf.text(`Префикс: ${dog.prefix_titles}`, margin, currentY);
                    currentY += 6;
                }
                if (dog.suffix_titles) {
                    pdf.text(`Суффикс: ${dog.suffix_titles}`, margin, currentY);
                    currentY += 6;
                }
                currentY += 5;
            }

            // Add other titles
            if (dog.other_titles) {
                pdf.setFontSize(10);
                pdf.text("Другие титулы:", margin, currentY);
                currentY += 6;

                pdf.setFontSize(10);
                pdf.text(dog.other_titles, margin + 5, currentY);
                currentY += 10;
            }

            // Add sports section
            if (dog.sports && dog.sports.length > 0) {
                if (currentY > pageHeight - 50) {
                    pdf.addPage();
                    currentY = 20;
                }

                pdf.setFontSize(12);
                pdf.text("Спортивные дисциплины:", margin, currentY);
                currentY += 8;

                pdf.setFontSize(10);
                dog.sports.forEach((sport) => {
                    pdf.text(`• ${sport}`, margin + 5, currentY);
                    currentY += 5;
                });
                currentY += 5;
            }

            // Add club information
            if (dog.club) {
                if (currentY > pageHeight - 30) {
                    pdf.addPage();
                    currentY = 20;
                }

                pdf.setFontSize(12);
                pdf.text("Питомник:", margin, currentY);
                currentY += 8;

                pdf.setFontSize(10);
                pdf.text(dog.club, margin, currentY);
                currentY += 10;
            }

            // Add parents section
            if (currentY > pageHeight - 60) {
                pdf.addPage();
                currentY = 20;
            }

            pdf.setFontSize(12);
            pdf.text("Родители:", margin, currentY);
            currentY += 8;

            pdf.setFontSize(10);

            // Father
            pdf.text("Отец:", margin, currentY);
            currentY += 6;
            pdf.text(dog.sire_name || "Неизвестно", margin + 5, currentY);
            currentY += 8;

            // Mother
            pdf.text("Мать:", margin, currentY);
            currentY += 6;
            pdf.text(dog.dam_name || "Неизвестно", margin + 5, currentY);
            currentY += 10;

            // Add health information
            if (
                dog.health_info_general?.length > 0 ||
                dog.health_info_genetic?.length > 0
            ) {
                if (currentY > pageHeight - 100) {
                    pdf.addPage();
                    currentY = 20;
                }

                pdf.setFontSize(20);
                pdf.text("Информация о здоровье:", pageWidth / 2, currentY, {
                    align: "center",
                });
                currentY += 8;

                // General health
                if (dog.health_info_general?.length > 0) {
                    pdf.setFontSize(10);
                    pdf.text("Общее здоровье:", margin, currentY);
                    currentY += 6;

                    pdf.setFontSize(10);
                    dog.health_info_general.forEach((test) => {
                        const result = test.screening_test_result || "N/A";
                        pdf.text(`${test.name}: ${result}`, margin + 5, currentY);
                        currentY += 5;
                    });
                    currentY += 5;
                }

                // Genetic health
                if (dog.health_info_genetic?.length > 0) {
                    if (currentY > pageHeight - 60) {
                        pdf.addPage();
                        currentY = 20;
                    }

                    pdf.setFontSize(10);
                    pdf.text("Генетические исследования:", margin, currentY);
                    currentY += 6;

                    pdf.setFontSize(10);
                    dog.health_info_genetic.forEach((test) => {
                        const result = test.notes || test.screening_test_result || "N/A";
                        pdf.text(`${test.name}: ${result}`, margin + 5, currentY);
                        currentY += 5;
                    });
                }
            }

            // Add pedigree tree image on a new page
            pdf.addPage();

            // Get the page content
            const dataUrl = await domtoimage.toPng(pedigreeTreeRef.current, {
                quality: 1.0,
                bgcolor: "#ffffff",
                width: pedigreeTreeRef.current.scrollWidth - 100,
                height: pedigreeTreeRef.current.scrollHeight,
                style: {
                    transform: "scale(1.2)",
                    transformOrigin: "top left",
                },
            });

            // Convert data URL to canvas
            const canvas = document.createElement("canvas");
            const ctx = canvas.getContext("2d");
            const img = new Image();
            await new Promise((resolve) => {
                img.onload = resolve;
                img.src = dataUrl;
            });
            canvas.width = img.width;
            canvas.height = img.height;
            ctx.drawImage(img, 0, 0);

            // Calculate dimensions for pedigree tree
            const imgWidth = pageWidth - 2 * margin;
            const imgHeight = (canvas.height * imgWidth) / canvas.width;

            // Add pedigree tree title
            pdf.setFontSize(20);
            pdf.text("Родословное дерево", pageWidth / 2, 20, { align: "center" });

            // Add the pedigree tree image
            const imgData = canvas.toDataURL("image/png");
            pdf.addImage(imgData, "PNG", margin, 30, imgWidth, imgHeight);

            // Save the PDF
            pdf.save(
                `dog_details_${dog.registered_name.replace(/[^a-zA-Z0-9]/g, "_")}.pdf`
            );
        } catch (error) {
            console.error("Ошибка при экспорте в PDF:", error);
            alert("Ошибка при создании PDF документа");
        } finally {
            setPdfLoading(false);
        }
    };

    // Handler for exporting dog data to JSON
    const handleExportToJSON = () => {
        try {
            const dataStr = JSON.stringify(dog, null, 2);
            const dataBlob = new Blob([dataStr], { type: "application/json" });
            const url = URL.createObjectURL(dataBlob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `dog_${dog.registered_name.replace(
                /[^a-zA-Z0-9]/g,
                "_"
            )}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error("Ошибка при экспорте в JSON:", error);
            alert("Ошибка при создании JSON файла");
        }
    };

    return {
        modalLoading,
        pdfLoading,
        handleExportToPNG,
        handleExportToPDF,
        handleExportToJSON,
    };
};