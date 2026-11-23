************************************************************
* AI agent sandbox analysis
* Scatterplots
************************************************************

clear all
set more off

* Set directory
cd

* Load table
import delimited using "/pilot_experiments/experiments_memory/output_memory.csv", clear varnames(1)

* Exclude case of unlimited memory (value=-1)
drop if value==-1

* Ensure the ratio and outcome are numeric if imported as strings.
destring value final_customers, replace force

sort value


twoway                                                    ///
    (scatter total_msg_received value,                    ///
        msymbol(circle)                                   ///
        msize(small)                                      ///
        mcolor(blue)                                      ///
        mlcolor(blue))                                     ///
    (lfit total_msg_received value,                       ///
        lcolor(gs6)                                        ///
        lpattern(dash)                                     ///
        lwidth(medthick))                                  ///
    ,                                                     ///
    xlabel(1(1)15, angle(0) labsize(large))               ///
    ylabel(, labsize(large) angle(0))                     ///
    xtitle(" " "Number of previous messages retained in context", size(large)) ///
    ytitle("Number of messages received", size(large)) ///
	subtitle("Panel A: {bf:Communication volume}", size(large)) ///
    legend(off)                                            ///
    graphregion(color(white))                             ///
    plotregion(color(white))                              ///
    scheme(s2color)                                       ///
    aspectratio(.40)                                      ///
    name(panel_a, replace)
graph export "results\scatter_memory_msg_received_261026.png", replace width(2000)
	

twoway                                                    ///
    (scatter authority_agents value,                    ///
        msymbol(circle)                                   ///
        msize(small)                                      ///
        mcolor(blue)                                      ///
        mlcolor(blue))                                     ///
    (lfit authority_agents value,                       ///
        lcolor(gs6)                                        ///
        lpattern(dash)                                     ///
        lwidth(medthick))                                  ///
    ,                                                     ///
    xlabel(1(1)15, angle(0) labsize(large))               ///
    ylabel(, labsize(large) angle(0))                     ///
    xtitle(" " "Number of previous messages retained in context", size(large)) ///
    ytitle("Number of agents w. authority", size(large)) ///
	subtitle("Panel B: {bf:Authority structure}", size(large)) ///
    legend(off)                                            ///
    graphregion(color(white))                             ///
    plotregion(color(white))                              ///
    scheme(s2color)                                       ///
    aspectratio(.40)                                      ///
    name(panel_b, replace)
graph export "results\scatter_memory_authority_agents_261026.png", replace width(2000)
	

twoway                                                    ///
    (scatter total_overallocated_hours value,                    ///
        msymbol(circle)                                   ///
        msize(small)                                      ///
        mcolor(blue)                                      ///
        mlcolor(blue))                                     ///
    (lfit total_overallocated_hours value,                       ///
        lcolor(gs6)                                        ///
        lpattern(dash)                                     ///
        lwidth(medthick))                                  ///
    ,                                                     ///
    xlabel(1(1)15, angle(0) labsize(large))               ///
    ylabel(, labsize(large) angle(0))                     ///
    xtitle(" " "Number of previous messages retained in context", size(large)) ///
    ytitle("Overallocated hours", size(large)) ///
	subtitle("Panel C: {bf:Inefficient work allocation}", size(large)) ///
    legend(off)                                            ///
    graphregion(color(white))                             ///
    plotregion(color(white))                              ///
    scheme(s2color)                                       ///
    aspectratio(.40)                                      ///
    name(panel_c, replace)
graph export "results\scatter_memory_overallocation_261026.png", replace width(2000)
	
twoway                                                    ///
    (scatter cumulative_customers value,                    ///
        msymbol(circle)                                   ///
        msize(small)                                      ///
        mcolor(blue)                                      ///
        mlcolor(blue))                                     ///
    (lfit cumulative_customers value,                       ///
        lcolor(gs6)                                        ///
        lpattern(dash)                                     ///
        lwidth(medthick))                                  ///
    ,                                                     ///
    xlabel(1(1)15, angle(0) labsize(large))               ///
    ylabel(, labsize(large) angle(0))                     ///
    xtitle(" " "Number of previous messages retained in context", size(large)) ///
    ytitle("Number of customers", size(large)) ///
	subtitle("Panel D: {bf:Customers generated}", size(large)) ///
    legend(off)                                            ///
    graphregion(color(white))                             ///
    plotregion(color(white))                              ///
    scheme(s2color)                                       ///
    aspectratio(.40)                                      ///
    name(panel_d, replace)	
graph export "results\scatter_memory_customers_cum_261026.png", replace width(2000)
	
