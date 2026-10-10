package com.vybe.app.navigation

/** Single source of truth for destinations. Bottom bar: Discover, Explore, Saved. */
object Destinations {
    const val SPLASH = "splash"
    const val LOGIN = "login"
    const val REGISTER = "register"
    const val SERVER = "server"
    const val DISCOVER = "discover"
    const val EXPLORE = "explore"
    const val DETAIL = "detail/{packageId}"
    const val SAVED = "saved"
    const val PREFS = "prefs"

    fun detail(id: Int) = "detail/$id"
}
