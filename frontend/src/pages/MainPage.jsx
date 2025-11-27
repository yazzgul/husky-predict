
import React, { useState, useEffect } from "react";
import { Box, Spinner } from "grommet";
import { useNavigate } from "react-router";

import notFoundDogImage from "../assets/images/notFoundDogImage.svg";
import { BACKEND_API_HOST } from "../constants";

export const MainPage = () => {
  const navigate = useNavigate();
  const [dogs, setDogs] = useState([]);
  const [meta, setMeta] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    search: "",
    country: "",
    color: "",
    neutered: false,
    frozen_semen: false,
    artificial_insemination: false,
    has_photo: false,
    has_conflicts: false,
  });
  const [sortBy, setSortBy] = useState("name_asc");
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 20;

  const getSortParams = (sortByValue) => {
    switch (sortByValue) {
      case "name_asc":
        return { sort_by: "registered_name", sort_order: "asc" };
      case "name_desc":
        return { sort_by: "registered_name", sort_order: "desc" };
      case "date_added_asc":
        return { sort_by: "modified_at", sort_order: "asc" };
      case "date_added_desc":
        return { sort_by: "modified_at", sort_order: "desc" };
      case "birth_date_asc":
        return { sort_by: "date_of_birth", sort_order: "asc" };
      case "birth_date_desc":
        return { sort_by: "date_of_birth", sort_order: "desc" };
      default:
        return { sort_by: "registered_name", sort_order: "asc" };
    }
  };

  useEffect(() => {
    const fetchDogs = async () => {
      try {
        setLoading(true);
        setError(null);

        const { sort_by, sort_order } = getSortParams(sortBy);
        const params = new URLSearchParams({
          page: currentPage,
          per_page: itemsPerPage,
          search: filters.search,
          land_of_birth: filters.country,
          color: filters.color,
          sort_by,
          sort_order,
        });

        // Add boolean filters only if they are true
        if (filters.neutered) params.append("neutered", "true");
        if (filters.frozen_semen) params.append("frozen_semen", "true");
        if (filters.artificial_insemination)
          params.append("artificial_insemination", "true");
        if (filters.has_photo) params.append("has_photo", "true");
        if (filters.has_conflicts) params.append("has_conflicts", "true");

        const response = await fetch(`${BACKEND_API_HOST}/dogs/?${params}`);

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        setDogs(data.data);
        setMeta(data.meta);
        setCurrentPage(data.meta.page);
      } catch (error) {
        setError(error.message);
        setDogs([]);
      } finally {
        setLoading(false);
      }
    };

    fetchDogs();
  }, [currentPage, filters, sortBy]);

  const handleFilterChange = (e) => {
    const { name, value } = e.target;
    setFilters((prev) => ({ ...prev, [name]: value }));
    setCurrentPage(1);
  };

  const handleCheckboxChange = (e) => {
    const { name, checked } = e.target;
    setFilters((prev) => ({ ...prev, [name]: checked }));
    setCurrentPage(1);
  };

  const handleSortChange = (e) => {
    setSortBy(e.target.value);
    setCurrentPage(1);
  };

  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= meta.total_pages) {
      setCurrentPage(newPage);
    }
  };

  return (
      <div className="min-h-screen w-full bg-gray-50 p-6">
        {/* Фильтры */}
        <div className="max-w-7xl mx-auto bg-white rounded-lg shadow-md p-6 py-4 mb-4">
          <h2 className="text-xl font-semibold text-gray-800 mb-3">Фильтры</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Поиск по имени
              </label>
              <input
                  type="text"
                  name="search"
                  value={filters.search}
                  onChange={handleFilterChange}
                  className="w-full px-3 py-1 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Введите имя собаки..."
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Страна рождения
              </label>
              <input
                  type="text"
                  name="country"
                  value={filters.country}
                  onChange={handleFilterChange}
                  className="w-full px-3 py-1 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Введите страну..."
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Окрас
              </label>
              <input
                  type="text"
                  name="color"
                  value={filters.color}
                  onChange={handleFilterChange}
                  className="w-full px-3 py-1 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Введите окрас..."
              />
            </div>
          </div>

          <div className="mt-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Сортировка
            </label>
            <select
                value={sortBy}
                onChange={handleSortChange}
                className="w-full px-3 py-1 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="name_asc">Имя (А-Я)</option>
              <option value="name_desc">Имя (Я-А)</option>
              <option value="date_added_asc">
                Дата добавления (сначала старые)
              </option>
              <option value="date_added_desc">
                Дата добавления (сначала новые)
              </option>
              <option value="birth_date_asc">
                Дата рождения (сначала старые)
              </option>
              <option value="birth_date_desc">
                Дата рождения (сначала новые)
              </option>
            </select>
          </div>

          {/* Чекбоксы фильтров */}
          <div className="mt-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Дополнительные фильтры
            </label>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              <label className="flex items-center cursor-pointer">
                <input
                    type="checkbox"
                    name="neutered"
                    checked={filters.neutered}
                    onChange={handleCheckboxChange}
                    className="mr-2 w-5 h-5 cursor-pointer accent-green-500 [&:checked]:bg-green-500 [&:checked]:border-green-500 [&:checked]:text-white"
                />
                <span className="text-sm text-gray-700 cursor-pointer">
                Кастрирован
              </span>
              </label>
              <label className="flex items-center cursor-pointer">
                <input
                    type="checkbox"
                    name="frozen_semen"
                    checked={filters.frozen_semen}
                    onChange={handleCheckboxChange}
                    className="mr-2 w-5 h-5 cursor-pointer accent-green-500 [&:checked]:bg-green-500 [&:checked]:border-green-500 [&:checked]:text-white"
                />
                <span className="text-sm text-gray-700 cursor-pointer">
                Замороженное семя
              </span>
              </label>
              <label className="flex items-center cursor-pointer">
                <input
                    type="checkbox"
                    name="artificial_insemination"
                    checked={filters.artificial_insemination}
                    onChange={handleCheckboxChange}
                    className="mr-2 w-5 h-5 cursor-pointer accent-green-500 [&:checked]:bg-green-500 [&:checked]:border-green-500 [&:checked]:text-white"
                />
                <span className="text-sm text-gray-700 cursor-pointer">
                Искусственное осеменение
              </span>
              </label>
              <label className="flex items-center cursor-pointer">
                <input
                    type="checkbox"
                    name="has_photo"
                    checked={filters.has_photo}
                    onChange={handleCheckboxChange}
                    className="mr-2 w-5 h-5 cursor-pointer accent-green-500 [&:checked]:bg-green-500 [&:checked]:border-green-500 [&:checked]:text-white"
                />
                <span className="text-sm text-gray-700 cursor-pointer">
                Есть фото
              </span>
              </label>
              <label className="flex items-center cursor-pointer">
                <input
                    type="checkbox"
                    name="has_conflicts"
                    checked={filters.has_conflicts}
                    onChange={handleCheckboxChange}
                    className="mr-2 w-5 h-5 cursor-pointer accent-green-500 [&:checked]:bg-green-500 [&:checked]:border-green-500 [&:checked]:text-white"
                />
                <span className="text-sm text-gray-700 cursor-pointer">
                Есть конфликты
              </span>
              </label>
            </div>
          </div>
        </div>
        <div className="md:max-h-[50vh] lg:max-h-[68vh] l max-w-7xl mx-auto mb-4 overflow-y-auto">
          <div className="space-y-4 pr-2">
            {loading && (
                <Box fill align="center" justify="center">
                  <Spinner size="medium" />
                </Box>
            )}
            {error && (
                <div className="text-center py-4 text-red-600">
                  Ошибка запроса: {error}
                </div>
            )}
            {!loading && !error && (
                <div className="grid gap-4 md:grid-cols-1 lg:grid-cols-1 xl:grid-cols-1">
                  {dogs.map((dog) => (
                      <div
                          key={dog.uuid}
                          className="bg-white rounded-lg shadow-md overflow-hidden cursor-pointer"
                          style={{ cursor: "pointer" }}
                          onClick={() => navigate(`/dog/${dog.id}`)}
                      >
                        <div className="md:flex">
                          {/* Фото собаки */}
                          <div className="md:w-1/4 p-4 flex items-center justify-center bg-gray-100">
                            <img
                                src={
                                    (dog.photo_url ? dog.photo_url.split(";")[0] : "") ||
                                    notFoundDogImage
                                }
                                alt="Собака"
                                className="max-w-full max-h-40 object-cover rounded"
                                onError={(e) => {
                                  console.log(dog.photo_url);
                                  e.target.src = notFoundDogImage;
                                }}
                            />
                          </div>

                          {/* Основная информация */}
                          <div className="md:w-3/4 p-4">
                            <div className="flex flex-col md:flex-row md:justify-between md:items-start">
                              <div>
                                <h3 className="text-xl font-bold text-gray-900">
                                  {dog.registered_name}
                                </h3>
                                {dog.call_name && (
                                    <p className="text-sm text-gray-600">
                                      "{dog.call_name}"
                                    </p>
                                )}
                              </div>

                              <div className="mt-2 md:mt-0 flex flex-wrap gap-2">
                                {dog.neutered && (
                                    <span className="px-2 py-1 bg-red-100 text-red-800 text-xs font-medium rounded-full">
                              Кастрирован
                            </span>
                                )}
                                {dog.approved_for_breeding && (
                                    <span className="px-2 py-1 bg-green-100 text-green-800 text-xs font-medium rounded-full">
                              Подтвержден для скрещивания
                            </span>
                                )}
                                {dog.frozen_semen && (
                                    <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs font-medium rounded-full">
                              Замороженное семя
                            </span>
                                )}
                                {dog.artificial_insemination && (
                                    <span className="px-2 py-1 bg-purple-100 text-purple-800 text-xs font-medium rounded-full">
                              Искусственное осеменение
                            </span>
                                )}
                              </div>
                            </div>

                            {/* Детали */}
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                              <div>
                                <p className="text-xs text-gray-500">Пол</p>
                                <p className="font-medium">
                                  {dog.sex === 1 ? "Мужской" : "Женский"}
                                </p>
                              </div>

                              <div>
                                <p className="text-xs text-gray-500">Год рождения</p>
                                <p className="font-medium">
                                  {dog.year_of_birth || "—"}
                                </p>
                              </div>

                              <div>
                                <p className="text-xs text-gray-500">Окрас</p>
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
                                <p className="text-xs text-gray-500">Страна</p>
                                <p className="font-medium">
                                  {dog.land_of_birth || "—"}
                                </p>
                              </div>
                            </div>

                            {/* COI и педигри */}
                            <div className="mt-4 flex flex-wrap gap-4">
                              {dog.coi !== null && (
                                  <p className="text-xs text-gray-500">
                                    COI: {dog.coi}% (Обновлено:{" "}
                                    {dog.coi_updated_on &&
                                        new Date(dog.coi_updated_on).toLocaleDateString()}
                                    )
                                  </p>
                              )}
                              {dog.incomplete_pedigree && (
                                  <p className="text-xs text-yellow-600">
                                    ⚠️ Неполная родословная
                                  </p>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                  ))}
                </div>
            )}
          </div>
        </div>

        {/* Пагинация */}
        {meta.total_pages > 1 && (
            <div className="max-w-7xl mx-auto mt-4 mb-4 flex justify-center items-center">
              <button
                  onClick={() => handlePageChange(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="px-3 py-1 mx-1 bg-gray-200 text-gray-700 rounded disabled:opacity-50"
              >
                Назад
              </button>

              <span className="mx-4 text-sm text-gray-600">
            Страница {currentPage} из {meta.total_pages}
          </span>

              <button
                  onClick={() => handlePageChange(currentPage + 1)}
                  disabled={currentPage === meta.total_pages}
                  className="px-3 py-1 mx-1 bg-gray-200 text-gray-700 rounded disabled:opacity-50"
              >
                Вперед
              </button>
            </div>
        )}
      </div>
  );
};

export default MainPage;
