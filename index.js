/**
 * @param {string} s
 * @return {number}
 */
var romanToInt = function(s) {
    const SYMBOLS = {
        I:1,
        V:5,
        X:10,
        L:50,
        C:100,
        D:500,
        M:1000,
        CM:900,
        XC:90,
        IV:4
    }
    
    let val = 0;
    let lastVal = ""
    for(const r of s.split("")){
        // if( Object.keys(SPECIAL_LETTER).find(v=>v.split('')===lastVal))
        val += SYMBOLS[r]
        lastVal = r
    }
    return val
};

console.log(romanToInt("MCMXCIV"))