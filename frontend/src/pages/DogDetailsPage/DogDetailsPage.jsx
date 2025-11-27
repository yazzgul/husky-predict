
import React, { useState, useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import { Box, Spinner } from "grommet";
import { Edit, Expand, Contract as Minimize } from "grommet-icons";

// Импортируем поддержку кириллицы для jsPDF
import "jspdf/dist/polyfills.es.js";

import { radioOptions, BACKEND_API_HOST } from "../../constants";
import {
  reverseTransformPedigreeStructure,
  convertHuskyUrl,
  formatDate,
  getStatusTags,
} from "../../utils";
import {
  DogDataConflictsModal,
  DogHistoryModal,
  NotesModal,
} from "../../components/modals";
import { PedigreeTree } from "../../components/PedigreeTree";
import { ManageTree } from "../../components/ManageTree";
import { ExportDropdown } from "../../components/ExportDropdown";
import { useDogInfoExportHandlers } from "../../hooks/useDogInfoExportHandlers";
import notFoundDogImage from "../../assets/images/notFoundDogImage.svg";
import "./DogDetailsPage.css";

export const DogDetailsPage = () => {
  const navigate = useNavigate();
  const { dogId } = useParams();

  const [dog, setDog] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentDogNode, setCurrentDogNode] = useState(null);
  const [pedigreeData, setPedigreeData] = useState(null);
  const [visibleAttribute, setVisibleAttribute] = useState(radioOptions[2]);
  const [showConflictsModal, setShowConflictsModal] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [coiLoading, setCoiLoading] = useState(false);
  const [currentPhotoIdx, setCurrentPhotoIdx] = useState(0);
  const [showNotesModal, setShowNotesModal] = useState(false);
  const [showTitlesAccordion, setShowTitlesAccordion] = useState(false);
  const [isTreeFullscreen, setIsTreeFullscreen] = useState(false);

  const pedigreeTreeRef = useRef(null);

  // Use custom hook for export handlers
  const {
    modalLoading: exportModalLoading,
    pdfLoading,
    handleExportToPNG,
    handleExportToPDF,
    handleExportToJSON,
  } = useDogInfoExportHandlers(dog, pedigreeTreeRef);

  // Получение статусных меток
  const statusTags = getStatusTags(dog);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [dogResponse, pedigreeResponse] = await Promise.all([
          axios.get(`${BACKEND_API_HOST}/dogs/${dogId}`),
          axios.get(`${BACKEND_API_HOST}/pedigree/${dogId}`),
        ]);

        setDog(dogResponse.data);
        setCurrentDogNode(pedigreeResponse.data);
        setPedigreeData(pedigreeResponse.data);
      } catch (error) {
        setError(error.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [dogId]);

  // Helper to refetch dog data
  const refetchDog = async () => {
    setLoading(true);
    try {
      const [dogResponse, pedigreeResponse] = await Promise.all([
        axios.get(`${BACKEND_API_HOST}/dogs/${dogId}`),
        axios.get(`${BACKEND_API_HOST}/pedigree/${dogId}`),
      ]);
      setDog(dogResponse.data);
      setCurrentDogNode(pedigreeResponse.data);
      setPedigreeData(pedigreeResponse.data);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  };

  // Handler for resolving conflicts
  const handleResolveConflicts = async (resolvedFields) => {
    setModalLoading(true);
    try {
      await axios.post(
          `${BACKEND_API_HOST}/dogs/${dogId}/resolve_conflicts`,
          resolvedFields
      );
      setShowConflictsModal(false);
      await refetchDog();
    } catch (e) {
      alert(
          "Ошибка при разрешении конфликтов: " +
          (e.response?.data?.detail || e.message)
      );
    } finally {
      setModalLoading(false);
    }
  };

  // Handler for undoing merge
  const handleUndoMerge = async (mergeLogId) => {
    setModalLoading(true);
    try {
      await axios.post(`${BACKEND_API_HOST}/dogs/${dogId}/undo_merge`, {
        merge_log_id: mergeLogId,
      });
      await refetchDog();
    } catch (e) {
      alert(
          "Ошибка при откате слияния: " + (e.response?.data?.detail || e.message)
      );
    } finally {
      setModalLoading(false);
    }
  };

  // Handler for refreshing COI
  const handleRefreshCOI = async () => {
    setCoiLoading(true);
    try {
      // First try to get current COI
      const response = await axios.get(`${BACKEND_API_HOST}/dogs/${dogId}/coi`);

      // If no COI data or coi_updated_on is null, calculate COI
      if (!response.data.coi || !response.data.coi_updated_on) {
        const calculateResponse = await axios.post(
            `${BACKEND_API_HOST}/dogs/${dogId}/calculate-coi`
        );
        // Update with calculated COI data
        setDog((prevDog) => ({
          ...prevDog,
          coi: calculateResponse.data.coi_percentage,
          coi_updated_on: calculateResponse.data.coi_updated_on,
        }));
      } else {
        // Update with existing COI data
        setDog((prevDog) => ({
          ...prevDog,
          coi: response.data.coi,
          coi_updated_on: response.data.coi_updated_on,
        }));
      }
    } catch (e) {
      alert(
          "Ошибка при обновлении COI: " + (e.response?.data?.detail || e.message)
      );
    } finally {
      setCoiLoading(false);
    }
  };

  // Получаем массив ссылок на фото
  const photoUrls = dog?.photo_url
      ? dog?.photo_url
          .split(";")
          .map((url) => url.trim())
          .filter(Boolean)
      : [];

  if (loading) {
    return (
        <Box fill align="center" justify="center">
          <Spinner size="large" />
        </Box>
    );
  }

  if (error) {
    return <div className="text-center py-8 text-red-600">Error: {error}</div>;
  }

  console.log(dog.titles);

  return (
      <div
          className={`flex flex-col h-screen w-full ${
              isTreeFullscreen ? "fixed inset-0 z-50 bg-white" : ""
          }`}
      >
        {/* Хлебные крошки */}
        {!isTreeFullscreen && (
            <div className="bg-white z-10">
              <div className="max-w-7xl mx-auto px-6 py-3">
                <nav className="flex" aria-label="Breadcrumb">
                  <ol className="inline-flex items-center space-x-1 md:space-x-3">
                    <li className="inline-flex items-center">
                      <a
                          href="/dogs"
                          className="inline-flex items-center text-sm font-medium text-gray-700 hover:text-blue-600"
                      >
                        Dogs
                      </a>
                    </li>
                    <li>
                      <div className="flex items-center">
                        <svg
                            className="w-4 h-4 text-gray-400"
                            fill="currentColor"
                            viewBox="0 0 20 20"
                        >
                          <path
                              fillRule="evenodd"
                              d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                              clipRule="evenodd"
                          />
                        </svg>
                        <span className="ml-1 text-sm font-medium text-gray-500 md:ml-2">
                      {dog.registered_name}
                    </span>
                      </div>
                    </li>
                  </ol>
                </nav>
              </div>
            </div>
        )}

        {/* Основной контент с прокруткой */}
        <div
            className={`flex-1 ${
                isTreeFullscreen ? "w-full h-full" : "max-w-90 overflow-y-auto"
            }`}
        >
          {/* Основная карточка */}
          {!isTreeFullscreen && (
              <div className="max-w-7xl bg-white rounded-lg shadow-md overflow-hidden mb-8 mt-6 mx-auto relative">
                <div className="max-w-7xl md:flex">
                  {/* Фото собаки */}
                  <div className="md:w-1/4 p-6">
                    {photoUrls.length > 1 ? (
                        <div className="relative flex flex-col items-center">
                          <img
                              src={
                                  convertHuskyUrl(photoUrls[currentPhotoIdx]) ||
                                  notFoundDogImage
                              }
                              alt={`Dog photo ${currentPhotoIdx + 1}`}
                              className="w-full h-auto rounded-lg object-cover"
                              onError={(e) => (e.target.src = notFoundDogImage)}
                          />
                          <div className="flex justify-center items-center gap-2 mt-2">
                            <button
                                className="px-2 py-1 bg-gray-200 rounded hover:bg-gray-300"
                                onClick={() =>
                                    setCurrentPhotoIdx(
                                        (idx) =>
                                            (idx - 1 + photoUrls.length) % photoUrls.length
                                    )
                                }
                                disabled={photoUrls.length <= 1}
                                aria-label="Предыдущее фото"
                            >
                              &#8592;
                            </button>
                            <span className="text-xs text-gray-600">
                        {currentPhotoIdx + 1} / {photoUrls.length}
                      </span>
                            <button
                                className="px-2 py-1 bg-gray-200 rounded hover:bg-gray-300"
                                onClick={() =>
                                    setCurrentPhotoIdx(
                                        (idx) => (idx + 1) % photoUrls.length
                                    )
                                }
                                disabled={photoUrls.length <= 1}
                                aria-label="Следующее фото"
                            >
                              &#8594;
                            </button>
                          </div>
                        </div>
                    ) : (
                        <img
                            src={
                                convertHuskyUrl(photoUrls[0] || "") || notFoundDogImage
                            }
                            alt="Dog"
                            className="w-full h-auto rounded-lg object-cover"
                            onError={(e) => (e.target.src = notFoundDogImage)}
                        />
                    )}
                  </div>
                  {/* Основная информация */}
                  <div className="md:w-3/4 p-6 relative">
                    {/* Иконка редактирования для notes/data_correctness_notes */}
                    {/* {(dog.notes || dog.data_correctness_notes) && ( */}
                    {/* )} */}
                    <div className="flex justify-between items-start mb-4">
                      <div>
                        <h1 className="text-3xl font-bold text-gray-900 flex">
                          <span>{dog.registered_name}</span>

                          <button
                              className="text-gray-400 hover:text-gray-600 ml-4 flex items-center"
                              onClick={() => setShowNotesModal(true)}
                              title="Показать заметки и корректность данных"
                          >
                            <Edit />
                          </button>
                        </h1>
                        {dog.call_name && (
                            <p className="text-lg text-gray-600">"{dog.call_name}"</p>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {statusTags.map((tag, index) => (
                            <span
                                key={index}
                                className={`px-3 py-1 rounded-full text-sm font-medium ${tag.color}`}
                            >
                        {tag.label}
                      </span>
                        ))}
                      </div>
                    </div>
                    {/* Детали */}
                    <div className="flex gap-8 mt-4">
                      <div className="flex-1 space-y-4">
                        <div>
                          <p className="text-sm text-gray-500">Пол</p>
                          <p className="font-medium">
                            {dog.sex === 1 ? "Мужской" : "Женский"}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-500">Окрас</p>
                          <p className="font-medium">
                            {dog.color ? (
                                <>
                                  {dog.color}
                                  {dog.color_marking && ` (${dog.color_marking})`}
                                </>
                            ) : (
                                "—"
                            )}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-500">Цвет глаз</p>
                          <p className="font-medium">{dog.eyes_color || "—"}</p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-500">Размер</p>
                          <p className="font-medium">{dog.size || "—"}</p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-500">Вес</p>
                          <p className="font-medium">{dog.weight || "—"}</p>
                        </div>
                      </div>
                      <div className="flex-1 space-y-4">
                        <div>
                          <p className="text-sm text-gray-500">Дата рождения</p>
                          <p className="font-medium">
                            {formatDate(dog.date_of_birth)}
                          </p>
                        </div>
                        {dog.date_of_death && (
                            <div>
                              <p className="text-sm text-gray-500">Дата смерти</p>
                              <p className="font-medium">
                                {formatDate(dog.date_of_death)}
                              </p>
                            </div>
                        )}
                        <div>
                          <p className="text-sm text-gray-500">Страна рождения</p>
                          <p className="font-medium">{dog.land_of_birth || "—"}</p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-500">Страна проживания</p>
                          <p className="font-medium">
                            {dog.land_of_standing || "—"}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-500">
                            Регистрационный номер
                          </p>
                          <p className="font-medium">
                            {dog.registration_number || "—"}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-500">Основной источник</p>
                          <p className="font-medium">{dog.source || "—"}</p>
                        </div>
                      </div>
                    </div>
                    {/* COI и педигри */}
                    <div className="mt-6">
                      <div className="flex items-center gap-2">
                        {dog && dog.coi !== null ? (
                            <p className="text-sm text-gray-500">
                              COI: {dog.coi}% (Обновлено:{" "}
                              {formatDate(dog.coi_updated_on, true)})
                            </p>
                        ) : (
                            <p className="text-sm text-gray-500">
                              Нет расчитанного COI
                            </p>
                        )}
                        <button
                            onClick={handleRefreshCOI}
                            disabled={coiLoading}
                            className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-50"
                            title="Обновить COI"
                        >
                          {coiLoading ? (
                              <svg
                                  className="animate-spin w-4 h-4"
                                  xmlns="http://www.w3.org/2000/svg"
                                  fill="none"
                                  viewBox="0 0 24 24"
                              >
                                <circle
                                    className="opacity-25"
                                    cx="12"
                                    cy="12"
                                    r="10"
                                    stroke="currentColor"
                                    strokeWidth="4"
                                ></circle>
                                <path
                                    className="opacity-75"
                                    fill="currentColor"
                                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                                ></path>
                              </svg>
                          ) : (
                              <svg
                                  xmlns="http://www.w3.org/2000/svg"
                                  width="16"
                                  height="16"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                              >
                                <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
                                <path d="M21 3v5h-5" />
                                <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
                                <path d="M3 21v-5h5" />
                              </svg>
                          )}
                        </button>
                      </div>
                      {dog.incomplete_pedigree && (
                          <div className="relative inline-block group">
                            <p className="text-sm text-yellow-600 cursor-help">
                              ⚠️ Неполная родословная
                            </p>
                            <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-800 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 whitespace-nowrap z-10">
                              Неполная родословная.
                              <br />
                              Для последних 5 поколений
                              <div className="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-800"></div>
                            </div>
                          </div>
                      )}
                    </div>
                    {/* Кнопки разрешения конфликтов и истории изменений */}
                    {dog?.has_conflicts &&
                        dog?.conflicts &&
                        Object.keys(dog.conflicts).length > 0 && (
                            <button
                                className="fixed md:absolute bottom-8 right-8 md:bottom-6 md:right-6 flex items-center gap-2 px-4 py-2 bg-gray-500 hover:bg-gray-400 text-white rounded shadow-lg z-50"
                                onClick={() => setShowConflictsModal(true)}
                                title="Разрешить конфликт"
                            >
                              <span>Разрешить конфликт</span>
                              <span>🔀</span>
                            </button>
                        )}
                    {!dog?.has_conflicts &&
                        dog?.merge_logs &&
                        dog.merge_logs.length > 0 && (
                            <button
                                className="fixed md:absolute bottom-8 right-8 md:bottom-6 md:right-6 flex items-center gap-2 px-4 py-2 bg-gray-500 hover:bg-gray-400 text-white rounded shadow-lg z-50"
                                onClick={() => setShowHistoryModal(true)}
                                title="История изменений"
                            >
                              <span>История изменений</span>
                              <span>🕓</span>
                            </button>
                        )}
                  </div>
                </div>
              </div>
          )}
          {!isTreeFullscreen && (
              <div className="max-w-7xl mx-auto">
                {/* Дополнительные секции */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  {/* Титулы */}
                  <div className="bg-white rounded-lg shadow-md p-6">
                    <h2 className="text-xl font-semibold text-gray-800 mb-4">
                      Титулы
                    </h2>
                    {dog.titles && dog.titles.length > 0 && (
                        <div className="mb-4">
                          <button
                              className="flex items-center gap-2 text-blue-600 hover:text-blue-800 font-medium"
                              onClick={() =>
                                  setShowTitlesAccordion(!showTitlesAccordion)
                              }
                          >
                            <span>Титулы ({dog.titles.length})</span>
                            <svg
                                className={`w-4 h-4 transition-transform ${
                                    showTitlesAccordion ? "rotate-180" : ""
                                }`}
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                            >
                              <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M19 9l-7 7-7-7"
                              />
                            </svg>
                          </button>
                          {showTitlesAccordion && (
                              <ul className="space-y-1 mt-2">
                                {dog.titles.map((title) => (
                                    <li
                                        key={title.id}
                                        className="flex items-center gap-2"
                                    >
                            <span className="font-regular text-blue-800">
                              {title.long_name}
                            </span>
                                      <span
                                          className="text-gray-600 font-regular"
                                          style={{ width: "75px" }}
                                      >
                              — {title.short_name}
                            </span>
                                      {title.has_winner_year && title.winner_year && (
                                          <span className="text-xs text-gray-500 ml-2">
                                ({title.winner_year})
                              </span>
                                      )}
                                      {title.is_prefix && (
                                          <span className="text-xs text-green-600 ml-2">
                                [Prefix]
                              </span>
                                      )}
                                      {!title.is_prefix && (
                                          <span className="text-xs text-purple-600 ml-2">
                                [Suffix]
                              </span>
                                      )}
                                    </li>
                                ))}
                              </ul>
                          )}
                        </div>
                    )}
                    {(dog.prefix_titles || dog.suffix_titles) && (
                        <div className="space-y-2 mt-2">
                          {dog.prefix_titles && (
                              <p className="font-medium">Prefix: {dog.prefix_titles}</p>
                          )}
                          {dog.suffix_titles && (
                              <p className="font-medium">Suffix: {dog.suffix_titles}</p>
                          )}
                        </div>
                    )}
                    {dog.other_titles && (
                        <div className="mt-2 text-gray-700">
                          <span className="font-medium">Другие титулы: </span>
                          {dog.other_titles}
                        </div>
                    )}
                  </div>

                  {/* Спортивные дисциплины */}
                  <div className="bg-white rounded-lg shadow-md p-6">
                    <h2 className="text-xl font-semibold text-gray-800 mb-4">
                      Спортивные дисциплины
                    </h2>
                    {dog.sports && dog.sports.length > 0 ? (
                        <ul className="space-y-2">
                          {dog.sports.map((sport, index) => (
                              <li key={index} className="border-b pb-2">
                                {sport}
                              </li>
                          ))}
                        </ul>
                    ) : (
                        <p className="text-gray-500">Нет записей</p>
                    )}
                  </div>

                  {/* Клуб */}
                  <div className="bg-white rounded-lg shadow-md p-6">
                    <h2 className="text-xl font-semibold text-gray-800 mb-4">
                      Питомник
                    </h2>
                    <p className={dog.club ? "font-medium" : "text-gray-500"}>
                      {dog.club || "Нет информации о питомнике"}
                    </p>
                  </div>
                </div>

                {/* Родители */}
                <div className="mt-6 bg-white rounded-lg shadow-md p-6">
                  <h2 className="text-xl font-semibold text-gray-800 mb-4">
                    Родители
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <h3 className="text-lg font-medium text-gray-700 mb-2">
                        Отец
                      </h3>
                      {dog.dam_name ? (
                          <div
                              className="p-3 border rounded"
                              style={{ cursor: dog.dam_id ? "pointer" : "auto" }}
                              onClick={() => {
                                if (dog.dam_id) {
                                  navigate(`/dog/${dog.dam_id}`, {
                                    preventScrollReset: true,
                                  });
                                }
                              }}
                          >
                            <p>{dog.dam_name}</p>
                            {dog.dam_uuid && (
                                <p className="text-sm text-gray-500">
                                  UUID: {dog.dam_uuid}
                                </p>
                            )}
                          </div>
                      ) : (
                          <p className="text-gray-500">Unknown</p>
                      )}
                    </div>
                    <div>
                      <h3 className="text-lg font-medium text-gray-700 mb-2">
                        Мать
                      </h3>
                      {dog.sire_name ? (
                          <div
                              className="p-3 border rounded"
                              style={{ cursor: dog.sire_id ? "pointer" : "auto" }}
                              onClick={() => {
                                if (dog.sire_id) {
                                  navigate(`/dog/${dog.sire_id}`, {
                                    preventScrollReset: true,
                                  });
                                }
                              }}
                          >
                            <p>{dog.sire_name}</p>
                            {dog.sire_uuid && (
                                <p className="text-sm text-gray-500">
                                  UUID: {dog.sire_uuid}
                                </p>
                            )}
                          </div>
                      ) : (
                          <p className="text-gray-500">Unknown</p>
                      )}
                    </div>
                  </div>
                </div>

                {/* Здоровье */}
                <div className="mt-6 bg-white rounded-lg shadow-md p-6">
                  <h2 className="text-xl font-semibold text-gray-800 mb-4">
                    Информация о здоровье
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Общие исследования */}
                    <div>
                      <h3 className="text-lg font-medium text-gray-700 mb-3">
                        Общее здоровье
                      </h3>
                      {dog.health_info_general?.length > 0 ? (
                          <div className="space-y-2">
                            {dog.health_info_general.map((test, index) => (
                                <div
                                    key={index}
                                    className="flex justify-between p-2 bg-gray-50 rounded"
                                >
                                  <span className="font-medium">{test.name}</span>
                                  <span className="text-gray-700">
                            {test.screening_test_result || "N/A"}
                          </span>
                                </div>
                            ))}
                          </div>
                      ) : (
                          <p className="text-gray-500">Нет данных о здоровье</p>
                      )}
                    </div>

                    {/* Генетические исследования */}
                    <div>
                      <h3 className="text-lg font-medium text-gray-700 mb-3">
                        Генетические исследования
                      </h3>
                      {dog.health_info_genetic?.length > 0 ? (
                          <div className="space-y-2">
                            {dog.health_info_genetic.map((test, index) => (
                                <div
                                    key={index}
                                    className="flex justify-between p-2 bg-gray-50 rounded"
                                >
                                  <span className="font-medium">{test.name}</span>
                                  <span className="text-gray-700">
                            {test.notes || test.screening_test_result || "N/A"}
                          </span>
                                </div>
                            ))}
                          </div>
                      ) : (
                          <p className="text-gray-500">
                            Нет данных о генетических исследованиях
                          </p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
          )}

          {/* Секция родословной */}
          <div
              className={`${
                  isTreeFullscreen
                      ? "w-full h-full"
                      : "mt-6 bg-white rounded-lg shadow-md p-6 mx-auto max-w-7xl"
              } relative`}
          >
            {/* Кнопка экспорта */}
            <div
                className={`absolute ${
                    !isTreeFullscreen ? "top-8 right-4" : "top-4 right-16"
                } z-10`}
            >
              <ExportDropdown
                  handleExportToPNG={handleExportToPNG}
                  handleExportToPDF={handleExportToPDF}
                  handleExportToJSON={handleExportToJSON}
                  modalLoading={exportModalLoading}
                  pdfLoading={pdfLoading}
              />
            </div>

            {!isTreeFullscreen && (
                <div className="flex flex-col gap-8">
                  <ManageTree
                      currentNode={currentDogNode}
                      visibleAttribute={visibleAttribute}
                      setVisibleAttribute={(attributeObj) =>
                          setVisibleAttribute(attributeObj)
                      }
                      radioOptions={radioOptions}
                  />
                </div>
            )}
            {pedigreeData && (
                <div
                    ref={pedigreeTreeRef}
                    className={isTreeFullscreen ? "w-full h-full" : ""}
                >
                  {/* Кнопка фокуса дерева */}
                  <div className="relative flex items-end justify-end top-4 right-4 z-1">
                    <button
                        onClick={() => setIsTreeFullscreen(!isTreeFullscreen)}
                        className="flex items-center gap-2 px-3 py-2 bg-gray-200 hover:bg-gray-300 text-white rounded-lg shadow-md"
                        title={
                          isTreeFullscreen ? "Свернуть дерево" : "Развернуть дерево"
                        }
                    >
                      {isTreeFullscreen ? (
                          <Minimize size="small" />
                      ) : (
                          <Expand size="small" />
                      )}
                    </button>
                  </div>

                  <PedigreeTree
                      pedigree={pedigreeData}
                      visibleAttribute={visibleAttribute}
                      currentNode={currentDogNode}
                      setCurrentNode={(nodeDatum) =>
                          setCurrentDogNode(
                              reverseTransformPedigreeStructure(nodeDatum)
                          )
                      }
                  />
                </div>
            )}
          </div>
        </div>
        {/* Модальные окна */}
        <DogDataConflictsModal
            open={showConflictsModal}
            onClose={() => setShowConflictsModal(false)}
            conflicts={dog?.conflicts}
            onSave={handleResolveConflicts}
            loading={modalLoading}
        />
        <DogHistoryModal
            open={showHistoryModal}
            onClose={() => setShowHistoryModal(false)}
            mergeLogs={dog?.merge_logs || []}
            onUndo={handleUndoMerge}
            loading={modalLoading}
        />
        {/* Модальное окно для notes/data_correctness_notes */}
        <NotesModal
            open={showNotesModal}
            onClose={() => setShowNotesModal(false)}
            dog={dog}
        />
      </div>
  );
};

export default DogDetailsPage;
