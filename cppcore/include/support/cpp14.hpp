#pragma once
#include <memory>
#include <type_traits>

// helper functions for use until C++14 brings this into std
namespace cpp14 {

template<class T, class... Args>
std::unique_ptr<T> make_unique(Args&&... args) {
    return std::unique_ptr<T>(new T(std::forward<Args>(args)...));
}

template<class T>
auto cbegin(const T& t) -> decltype(t.cbegin()) {
    return t.cbegin();
}

template<class T>
auto cend(const T& t) -> decltype(t.cend()) {
    return t.cend();
}

template <bool condition, class T = void>
using enable_if_t = typename std::enable_if<condition, T>::type;

} // end namespace cpp14